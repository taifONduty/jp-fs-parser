"""A table as a Docling engine returns it, and its conversion into the jpfs intermediate
representation.

Every Docling engine emits Grids. Everything after this point (tree, cross-page titles,
verification) is shared with the geometry engine, so engines differ in table reading alone.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from html.parser import HTMLParser
from itertools import pairwise
from statistics import median

from jpfs.model import Amount, Cell, Header, Period, Row, Table
from jpfs.structure import build_structure
from jpfs.text import (
    NOTE_RE,
    UNIT_SCALES,
    find_correction,
    find_title,
    find_unit,
    normalize,
    note_markers,
    parse_amount,
    parse_period,
)

INDENT_TOLERANCE = 2.5  # pt between label starts on one indentation level
LINE_TOLERANCE = 2.5  # pt between word tops on one text-layer line
_NO_BOX = (0.0, 0.0, 0.0, 0.0)


@dataclass(frozen=True)
class GridCell:
    text: str
    x0: float | None = None  # left edge of the cell's text on the page, when known


@dataclass(frozen=True)
class Grid:
    rows: tuple[tuple[GridCell, ...], ...]
    context: str  # page text above the table: titles, unit lines, 訂正 markers


def parse_html_table(html: str) -> list[list[str]]:
    """Rows of cell texts from a model's HTML table. A colspan repeats the cell; rowspans are
    ignored."""

    class Parser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.rows: list[list[str]] = []
            self.cell: list[str] | None = None
            self.span = 1

        def handle_starttag(self, tag: str, attrs: list) -> None:
            if tag == "tr":
                self.rows.append([])
            elif tag in ("td", "th"):
                self.cell = []
                self.span = int(dict(attrs).get("colspan", 1) or 1)

        def handle_endtag(self, tag: str) -> None:
            if tag in ("td", "th") and self.cell is not None and self.rows:
                self.rows[-1] += ["".join(self.cell).strip()] * self.span
                self.cell = None

        def handle_data(self, data: str) -> None:
            if self.cell is not None:
                self.cell.append(data)

    parser = Parser()
    parser.feed(html)
    return [row for row in parser.rows if row]


def to_table(grid: Grid, page_text: str) -> Table | None:
    """The jpfs Table for a grid: header rows above the first amount, value columns where amounts
    are, periods from the header text above each value column, levels from label positions."""
    rows = [list(row) for row in grid.rows]
    width = max((len(row) for row in rows), default=0)
    rows = [row + [GridCell("")] * (width - len(row)) for row in rows]
    first = next((i for i, row in enumerate(rows) if any(_amount(c) for c in row[1:])), None)
    if first is None:
        return None
    value_columns = [c for c in range(1, width) if any(_amount(row[c]) for row in rows[first:])]
    head = [row for row in rows[:first] if any(row[c].text.strip() for c in value_columns)]
    body = [row for row in rows[:first] if row not in head] + rows[first:]
    header_texts = {c: "".join(row[c].text for row in head) for c in value_columns}
    slots: dict[int, int] = {}
    periods: list[Period] = []
    note_columns: set[int] = set()
    for c in value_columns:
        text = header_texts[c]
        period = parse_period(text) if text else Period("", end=None)
        if period:
            slots[c] = len(periods)
            periods.append(period)
        elif "注" in normalize(text):
            note_columns.add(c)

    built: list[Row] = []
    unplaced: list[str] = []
    for row in body:
        built_row, lost = _row(row, value_columns, slots, note_columns, len(periods))
        unplaced += lost
        if built_row is not None:
            built.append(built_row)
    linked, warnings = build_structure(_levelled(built))
    title = next(
        (t for line in reversed(grid.context.splitlines()) if (t := find_title(line))), None
    )
    unit = (
        find_unit(grid.context) or find_unit("".join(header_texts.values())) or find_unit(page_text)
    )
    header = Header(
        title=title[0] if title else None,
        kind=title[1] if title else None,
        consolidated="連結" in title[0] if title else None,
        correction=find_correction(grid.context) or find_correction(page_text),
        unit=unit if unit in UNIT_SCALES else None,
    )
    return Table(header, tuple(periods), linked, tuple(unplaced), warnings)


def _amount(cell: GridCell) -> Amount | None:
    text = normalize(cell.text)
    return parse_amount(text) if text else None


def _row(
    cells: Sequence[GridCell],
    value_columns: Sequence[int],
    slots: dict[int, int],
    note_columns: set[int],
    n_periods: int,
) -> tuple[Row | None, list[str]]:
    label_parts: list[GridCell] = []
    amounts: list[Cell | None] = [None] * n_periods
    notes: list[str] = []
    unplaced: list[str] = []
    for c, cell in enumerate(cells):
        text = cell.text.strip()
        if not text:
            continue
        if c in note_columns or NOTE_RE.fullmatch(normalize(text)):
            notes += note_markers(text) or [normalize(text)]
        elif c in slots:
            amount = _amount(GridCell(NOTE_RE.sub("", text)))
            if amount is None:
                unplaced.append(f"cell '{text}' is not an amount")
            else:
                amounts[slots[c]] = Cell(amount, text, _NO_BOX)
        elif c not in value_columns:
            label_parts.append(cell)
    raw = "".join(p.text for p in label_parts)
    label = NOTE_RE.sub("", raw).strip()
    if not label and not any(amounts):
        return None, unplaced
    x0 = next((p.x0 for p in label_parts if p.x0 is not None), None)
    bbox = (x0, 0.0, x0, 0.0) if x0 is not None else _NO_BOX
    return Row(label, bbox, tuple(amounts), notes=tuple(notes + note_markers(raw))), unplaced


def _levelled(rows: Sequence[Row]) -> list[Row]:
    """Levels from label positions quantised by the table's own indentation step; rows without a
    position stay at the level of the row above."""
    starts = sorted(row.bbox[0] for row in rows if row.bbox != _NO_BOX)
    centres: list[float] = []
    for x in starts:
        if centres and x - centres[-1] <= INDENT_TOLERANCE:
            continue
        centres.append(x)
    step = median(b - a for a, b in pairwise(centres)) if len(centres) > 1 else 1.0
    base = centres[0] if centres else 0.0
    levels: list[int] = []
    for row in rows:
        if row.bbox == _NO_BOX:
            levels.append(levels[-1] if levels else 0)
        else:
            levels.append(max(0, round((row.bbox[0] - base) / step)))
    return [replace(row, level=level) for row, level in zip(rows, levels, strict=True)]


def grounded(
    rows: Sequence[Sequence[str]], words: Sequence[dict]
) -> tuple[tuple[GridCell, ...], ...]:
    """Attach each model row's indentation by finding its text-layer line in order: by its amounts
    when it has any, else by its label. Only the line's left edge is taken from the text layer;
    labels and values stay as the model read them."""
    lines = _text_lines(words)
    cells = []
    cursor = 0
    for row in rows:
        texts = [normalize(t) for t in row]
        figures = [re.sub(r"\D", "", t) for t in texts if t and parse_amount(t)]
        label = next((t for t in texts if t and not parse_amount(t)), "")
        x0 = None
        for i in range(cursor, len(lines)):
            left, text, line_figures = lines[i]
            if (figures and figures == line_figures[-len(figures) :]) or (
                not figures and label and text.startswith(label[:4])
            ):
                x0, cursor = left, i + 1
                break
        cells.append(tuple(GridCell(text, x0 if c == 0 else None) for c, text in enumerate(row)))
    return tuple(cells)


def _text_lines(words: Sequence[dict]) -> list[tuple[float, str, list[str]]]:
    """Text-layer lines, top to bottom: left edge, normalised text and the digits of each
    amount."""
    groups: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if groups and w["top"] - groups[-1][0]["top"] <= LINE_TOLERANCE:
            groups[-1].append(w)
        else:
            groups.append([w])
    lines = []
    for group in groups:
        group.sort(key=lambda w: w["x0"])
        texts = [normalize(w["text"]) for w in group]
        figures = [re.sub(r"\D", "", t) for t in texts if parse_amount(t)]
        lines.append((group[0]["x0"], "".join(texts), figures))
    return lines
