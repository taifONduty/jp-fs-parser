"""Gold transcriptions: one TSV line per printed row with its level, label and per-period values.

# meta: title=連結貸借対照表 unit=千円 p0=前連結会計年度@2025-03-31 p1=当連結会計年度@2026-03-31
2	現金及び預金	2,002,429	608,281
"""

from dataclasses import replace
from datetime import date
from pathlib import Path

from jpfs.model import Cell, Header, Period, Row, Table
from jpfs.structure import build_structure
from jpfs.text import UNIT_SCALES, find_title, parse_amount

_NO_BOX = (0.0, 0.0, 0.0, 0.0)


def load_gold(path: Path) -> Table:
    meta: dict[str, str] = {}
    rows: list[Row] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.startswith("# meta:"):
            meta = dict(item.split("=", 1) for item in line.removeprefix("# meta:").split())
        elif line.strip() and not line.startswith("#"):
            level, label, *values = line.split("\t")
            cells = tuple(_cell(value, path, number) for value in values)
            rows.append(Row(label, _NO_BOX, cells, level=int(level)))

    keys = sorted((k for k in meta if k[0] == "p" and k[1:].isdigit()), key=lambda k: int(k[1:]))
    periods = tuple(_period(meta[k]) for k in keys)
    rows = [row if len(row.cells) == len(periods) else _padded(row, len(periods)) for row in rows]
    linked, _ = build_structure(rows)
    title = find_title(meta["title"])
    unit = meta["unit"]
    header = Header(
        title=title[0] if title else meta["title"],
        kind=title[1] if title else None,
        consolidated="連結" in meta["title"],
        correction=meta.get("correction"),
        unit=unit,
        scale=UNIT_SCALES[unit],
    )
    return Table(header, periods, linked)


def _cell(value: str, path: Path, line: int) -> Cell | None:
    if not value.strip():
        return None
    amount = parse_amount(value)
    if amount is None:
        raise ValueError(f"{path}:{line}: not an amount: {value!r}")
    return Cell(amount, value, _NO_BOX)


def _period(spec: str) -> Period:
    label, _, end = spec.partition("@")
    return Period(label, date.fromisoformat(end) if end else None)


def _padded(row: Row, width: int) -> Row:
    return replace(row, cells=(row.cells + (None,) * width)[:width])
