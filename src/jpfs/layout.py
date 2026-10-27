"""Path A of the design (S2, S3a): statement tables from the PDF text layer and vector graphics.

A page is read as words and visible strokes and split into statements at their titles. Each
statement becomes a Table: value columns from the right edges of amounts, periods from the column
headers, rows from baselines, levels from indentation, and cues from rules and underlines.
"""

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from itertools import pairwise
from statistics import median

from pdfplumber.page import Page

from jpfs.model import Amount, BBox, Cell, Header, Period, Row, StatementKind, Table
from jpfs.structure import build_structure
from jpfs.text import (
    NOTE_RE,
    find_correction,
    find_title,
    find_unit,
    normalize,
    note_markers,
    parse_amount,
    parse_period,
    unit_line,
)

INK = 0.5  # strokes darker than this luminance are visible rules
BACKGROUND = 0.95  # glyphs lighter than this are painted in the background colour
RULE_HEIGHT = 1.5  # pt; taller shapes are fills, not rules
LINE_TOLERANCE = 2.0  # pt between word tops on one baseline
COLUMN_TOLERANCE = 8.0  # pt between right edges of amounts in one column
MIN_COLUMN_SIZE = 3  # amounts needed to establish a value column
INDENT_TOLERANCE = 2.5  # pt between label starts on one indentation level
LABEL_AREA = 0.3  # share of the page width, from the left, where labels start
RULE_SPAN = 0.9  # share of a column a summation rule spans
UNDERLINE_SPAN = 0.6  # share of a figure's width a correction underline spans
UNDERLINE_GAP = 4.0  # pt below a figure within which an underline belongs to it


@dataclass(frozen=True, slots=True)
class Word:
    text: str
    x0: float
    top: float
    x1: float
    bottom: float

    @property
    def bbox(self) -> BBox:
        return (self.x0, self.top, self.x1, self.bottom)

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass(frozen=True, slots=True)
class Rule:
    x0: float
    top: float
    x1: float


@dataclass(frozen=True, slots=True)
class PageContent:
    words: tuple[Word, ...]
    rules: tuple[Rule, ...]
    width: float
    text: str  # every glyph on the page, for the text-layer audit and page-level cues


@dataclass(frozen=True, slots=True)
class _Column:
    x0: float
    x1_min: float  # the right edges of the column's figures span x1_min..x1
    x1: float

    def holds(self, word: Word, amount: Amount) -> bool:
        """Amounts are right-aligned; nil marks may sit anywhere in the column."""
        if amount.nil:
            return self.x0 - COLUMN_TOLERANCE <= word.cx <= self.x1 + COLUMN_TOLERANCE
        return self.x1_min - COLUMN_TOLERANCE <= word.x1 <= self.x1 + COLUMN_TOLERANCE


Line = tuple[Word, ...]


def read_page(page: Page) -> PageContent:
    """Visible words and rules; simulated-bold duplicates and background-coloured ink dropped."""
    visible = page.dedupe_chars().filter(_is_visible)
    words = tuple(
        Word(w["text"], w["x0"], w["top"], w["x1"], w["bottom"])
        for w in visible.extract_words(x_tolerance=1.5)
    )
    shapes = [
        (r, r["non_stroking_color"] if r["fill"] else r["stroking_color"]) for r in page.rects
    ]
    shapes += [(line, line["stroking_color"]) for line in page.lines]
    rules = tuple(
        Rule(shape["x0"], shape["top"], shape["x1"])
        for shape, colour in shapes
        if shape["bottom"] - shape["top"] < RULE_HEIGHT and luminance(colour) < INK
    )
    return PageContent(words, rules, float(page.width), "".join(c["text"] for c in page.chars))


def luminance(colour: object) -> float:
    """0 for black, 1 for white. PDF paints black when no colour is set; patterns count as ink."""
    if colour is None:
        return 0.0
    c = tuple(colour) if isinstance(colour, (tuple, list)) else (colour,)
    if not all(isinstance(x, (int, float)) for x in c):
        return 0.0
    match c:
        case (gray,):
            return float(gray)
        case (r, g, b):
            return 0.299 * r + 0.587 * g + 0.114 * b
        case (cyan, magenta, yellow, black):
            return luminance(tuple((1 - x) * (1 - black) for x in (cyan, magenta, yellow)))
    return 0.0


def _is_visible(obj: dict) -> bool:
    return obj["object_type"] != "char" or luminance(obj.get("non_stroking_color")) < BACKGROUND


def extract_tables(content: PageContent) -> list[Table]:
    label_edge = content.width * LABEL_AREA
    tables: list[Table] = []
    above = ""  # text of the page above the current statement, for its 訂正 marker
    for segment in _segments(_lines(content.words), label_edge):
        table = _table(segment, content, label_edge, above)
        if table is not None:
            tables.append(table)
        above += "".join(_text(line) for line in segment)
    return tables


def statement_titles(content: PageContent) -> list[str]:
    label_edge = content.width * LABEL_AREA
    return [title[0] for line in _lines(content.words) if (title := _title(line, label_edge))]


def _lines(words: Iterable[Word]) -> list[Line]:
    groups = _clusters(words, key=lambda w: w.top, tolerance=LINE_TOLERANCE)
    return [_merge_fragments(sorted(group, key=lambda w: w.x0)) for group in groups]


_FRAGMENT_RE = re.compile(r"[△▲\-−(),.\d]+")
_FIGURE_RE = re.compile(r"[△▲\-−(]?\d[\d,.]*\)?%?")


def _merge_fragments(line: Sequence[Word]) -> Line:
    """Rejoin amounts that a producer emitted in pieces, such as '2,' '002,' '429'."""
    merged: list[Word] = []
    for w in line:
        prev = merged[-1] if merged else None
        if (
            prev is not None
            and _FRAGMENT_RE.fullmatch(normalize(prev.text))
            and _FRAGMENT_RE.fullmatch(normalize(w.text))
            and w.x0 - prev.x1 < (w.bottom - w.top) / 2
        ):
            merged[-1] = Word(
                prev.text + w.text, prev.x0, min(prev.top, w.top), w.x1, max(prev.bottom, w.bottom)
            )
        else:
            merged.append(w)
    return tuple(merged)


def _segments(lines: Sequence[Line], label_edge: float) -> list[list[Line]]:
    """Split before each statement title; a leading untitled segment continues a statement."""
    segments: list[list[Line]] = [[]]
    for line in lines:
        if segments[-1] and _title(line, label_edge):
            segments.append([])
        segments[-1].append(line)
    return segments


def _title(line: Line, label_edge: float) -> tuple[str, StatementKind] | None:
    """A heading naming a statement; enumerators such as （１） are not amounts here."""
    if any(_amount(w, label_edge) for w in line):
        return None
    return find_title(_text(line))


def _table(
    lines: Sequence[Line], content: PageContent, label_edge: float, above: str
) -> Table | None:
    columns = _columns(lines, label_edge)
    held = [
        i
        for i, line in enumerate(lines)
        if any(_column_of(w, columns, label_edge) is not None for w in line)
    ]
    if not held:
        return None
    last = max(held[-1], *_figure_lines(lines, columns))
    head = [i for i in range(held[0]) if _is_head(lines[i], label_edge)]
    header_lines = [
        tuple(w for w in lines[i] if w.x0 > label_edge)
        for i in head
        if not _title(lines[i], label_edge) and not find_unit(_text(lines[i]))
    ]
    periods, slots, note_columns = _periods(header_lines, columns)

    rows: list[Row] = []
    unplaced: list[str] = []
    unit = None  # set by a unit line inside the body, e.g. (単位：円) above per-share rows
    for line in lines[max(head, default=-1) + 1 : last + 1]:
        if stated := unit_line(_text(line)):
            unit = stated
            continue
        row, lost = _row(line, columns, slots, note_columns, len(periods), label_edge)
        unplaced += lost
        if row is not None:
            rows.append(replace(row, unit=unit))
    linked, warnings = build_structure(_with_cues(_with_levels(rows), content.rules, columns))
    header = _header(lines[: held[0]], label_edge, above, content.text)
    return Table(header, periods, linked, tuple(unplaced), warnings)


def _figure_lines(lines: Sequence[Line], columns: Sequence[_Column]) -> list[int]:
    """Lines with a figure under the value columns, readable or not: the body runs to the last."""
    lo, hi = columns[0].x0 - COLUMN_TOLERANCE, columns[-1].x1 + COLUMN_TOLERANCE
    return [
        i
        for i, line in enumerate(lines)
        if any(lo <= w.x1 <= hi and _FIGURE_RE.fullmatch(normalize(w.text)) for w in line)
    ]


def _is_head(line: Line, label_edge: float) -> bool:
    values = [w for w in line if w.x0 > label_edge]
    return (
        _title(line, label_edge) is not None
        or len(values) == len(line)
        or parse_period(_text(values)) is not None
    )


def _header(preamble: Sequence[Line], label_edge: float, above: str, page_text: str) -> Header:
    title = _title(preamble[0], label_edge) if preamble else None
    text = "".join(_text(line) for line in preamble)
    return Header(
        title=title[0] if title else None,
        kind=title[1] if title else None,
        consolidated="連結" in title[0] if title else None,
        correction=find_correction(above + text),
        unit=find_unit(text) or find_unit(page_text),
    )


def _columns(lines: Sequence[Line], label_edge: float) -> list[_Column]:
    figures = [
        w for line in lines for w in line if (a := _amount(w, label_edge)) is not None and not a.nil
    ]
    groups = _clusters(figures, key=lambda w: w.x1, tolerance=COLUMN_TOLERANCE)
    return [
        _Column(min(w.x0 for w in group), group[0].x1, group[-1].x1)
        for group in groups
        if len(group) >= MIN_COLUMN_SIZE
    ]


def _amount(word: Word, label_edge: float) -> Amount | None:
    return parse_amount(word.text) if word.x0 > label_edge else None


def _column_of(word: Word, columns: Sequence[_Column], label_edge: float) -> int | None:
    amount = _amount(word, label_edge)
    if amount is None:
        return None
    return next((i for i, column in enumerate(columns) if column.holds(word, amount)), None)


def _periods(
    header_lines: Sequence[Line], columns: Sequence[_Column]
) -> tuple[tuple[Period, ...], list[int | None], frozenset[int]]:
    """Periods read from the header words above each column, each column's period slot, and the
    columns that hold note references.

    Figures are right-aligned while headers are centred over the whole cell, so a column owns
    the space between the previous column's right edge and its own. A column whose header names
    no period gets no slot: a 注記 column holds note references, and any other one holds figures
    the parser cannot bind. A column without a header gets an anonymous period, so that its
    amounts are kept and the page is sent to review.
    """
    texts = [""] * len(columns)
    for line in header_lines:
        for w in line:
            owner = next(
                (i for i, c in enumerate(columns) if w.cx <= c.x1 + COLUMN_TOLERANCE),
                len(columns) - 1,
            )
            texts[owner] += w.text
    periods: list[Period] = []
    slots: list[int | None] = []
    for text in texts:
        period = parse_period(text) if text else Period("", end=None)
        slots.append(len(periods) if period else None)
        if period:
            periods.append(period)
    note_columns = frozenset(i for i, text in enumerate(texts) if "注" in normalize(text))
    return tuple(periods), slots, note_columns


def _row(
    line: Line,
    columns: Sequence[_Column],
    slots: Sequence[int | None],
    note_columns: frozenset[int],
    n_periods: int,
    label_edge: float,
) -> tuple[Row | None, list[str]]:
    """A row from one line, and the printed content on it that could not be bound to a cell."""
    label_words: list[Word] = []
    notes: list[Word] = []
    cells: list[Cell | None] = [None] * n_periods
    unplaced: list[str] = []
    for w in line:
        amount = _amount(w, label_edge)
        column = _column_of(w, columns, label_edge)
        slot = slots[column] if column is not None else None
        if NOTE_RE.fullmatch(normalize(w.text)):
            notes.append(w)
        elif amount is None and w.x0 > label_edge and _FIGURE_RE.fullmatch(normalize(w.text)):
            unplaced.append(f"figure '{w.text}' is not an amount (decimal or ratio?)")
        elif amount is None:
            label_words.append(w)
        elif column is None:
            unplaced.append(f"amount '{w.text}' at x={w.x1:.0f} lies outside every value column")
        elif slot is None and column in note_columns:
            notes.append(w)
        elif slot is None:
            unplaced.append(f"amount '{w.text}' in a column whose header names no period")
        elif cells[slot] is not None:
            unplaced.append(f"two amounts in one cell: '{cells[slot].text}' and '{w.text}'")
        else:
            cells[slot] = Cell(amount, w.text, w.bbox)

    raw = "".join(w.text for w in label_words)
    label = NOTE_RE.sub("", raw).strip()
    if not label and not any(cells):
        return None, unplaced
    if not label:
        unplaced.append(f"row without a label at y={line[0].top:.0f}")
    markers = [m for w in notes for m in note_markers(w.text) or [normalize(w.text)]]
    markers += note_markers(raw)
    return Row(label, _union(label_words or line), tuple(cells), notes=tuple(markers)), unplaced


def _with_levels(rows: Sequence[Row]) -> list[Row]:
    """Quantise label starts into levels by the page's own indentation step."""
    starts = [row.bbox[0] for row in rows if row.label]
    centres = [median(group) for group in _clusters(starts, key=float, tolerance=INDENT_TOLERANCE)]
    step = median(b - a for a, b in pairwise(centres)) if len(centres) > 1 else 1.0
    base = centres[0] if centres else 0.0
    levels: list[int] = []
    for row in rows:
        own = max(0, round((row.bbox[0] - base) / step))
        levels.append(own if row.label else (levels[-1] if levels else 0))
    return [replace(row, level=level) for row, level in zip(rows, levels, strict=True)]


def _with_cues(rows: Sequence[Row], rules: Sequence[Rule], columns: Sequence[_Column]) -> list[Row]:
    """Mark rows with a summation rule above them and cells with a correction underline.

    A ruled total or net is usually ruled below as well; that closing rule belongs to it, so the
    row after a ruled row is not itself ruled by the same gap.
    """
    cued: list[Row] = []
    for i, row in enumerate(rows):
        top, bottom = row.bbox[1], row.bbox[3]
        gap_top = rows[i - 1].bbox[3] if i else top - (bottom - top)
        ruled = any(
            gap_top - 1 <= r.top <= top + 1 and any(_spans(r, c) for c in columns) for r in rules
        )
        cells = tuple(
            None if cell is None else replace(cell, corrected=_underlined(cell, rules))
            for cell in row.cells
        )
        closing_rule_of_previous = bool(cued) and cued[-1].rule_above
        cued.append(replace(row, rule_above=ruled and not closing_rule_of_previous, cells=cells))
    return cued


def _spans(rule: Rule, column: _Column) -> bool:
    overlap = min(rule.x1, column.x1) - max(rule.x0, column.x0)
    return overlap >= RULE_SPAN * (column.x1 - column.x0)


def _underlined(cell: Cell, rules: Sequence[Rule]) -> bool:
    """A 訂正箇所 underline is glyph-wide and directly below the figure, unlike a column rule."""
    x0, _, x1, bottom = cell.bbox
    return any(
        bottom - 1 <= r.top <= bottom + UNDERLINE_GAP
        and r.x0 >= x0 - COLUMN_TOLERANCE / 2
        and r.x1 <= x1 + COLUMN_TOLERANCE / 2
        and r.x1 - r.x0 >= UNDERLINE_SPAN * (x1 - x0)
        for r in rules
    )


def _clusters[T](items: Iterable[T], key: Callable[[T], float], tolerance: float) -> list[list[T]]:
    """Single-linkage groups of items whose keys lie within tolerance of a neighbour."""
    groups: list[list[T]] = []
    for item in sorted(items, key=key):
        if groups and key(item) - key(groups[-1][-1]) <= tolerance:
            groups[-1].append(item)
        else:
            groups.append([item])
    return groups


def _text(words: Iterable[Word]) -> str:
    return "".join(w.text for w in words)


def _union(words: Sequence[Word]) -> BBox:
    return (
        min(w.x0 for w in words),
        min(w.top for w in words),
        max(w.x1 for w in words),
        max(w.bottom for w in words),
    )
