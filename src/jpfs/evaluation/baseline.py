"""Off-the-shelf baseline: pdfplumber's own table finder on the same page.

It shows why grid metrics are not enough: the body cells can come back intact while the
periods, the unit and the hierarchy that give them meaning are lost.
"""

from collections import Counter
from pathlib import Path

import pdfplumber

from jpfs.model import Table
from jpfs.text import normalize, parse_amount

STRATEGIES = {
    "pdfplumber, ruling lines": {},
    "pdfplumber, text alignment": {"vertical_strategy": "text", "horizontal_strategy": "text"},
}


def baseline(pdf: Path, page: int, gold: Table) -> dict:
    expected = Counter(
        (normalize(row.label), tuple(c.amount for c in row.cells if c is not None))
        for row in gold.rows
    )
    report = {}
    with pdfplumber.open(pdf) as document:
        for name, settings in STRATEGIES.items():
            grid = max(document.pages[page - 1].extract_tables(settings), key=len, default=[])
            found = Counter(_flat(row) for row in grid)
            text = normalize("".join(cell or "" for row in grid for cell in row))
            report[name] = {
                "rows_reproduced": f"{(expected & found).total()}/{len(gold.rows)}",
                "period_dates_kept": all(
                    f"{p.end.year}年{p.end.month}月{p.end.day}日" in text
                    for p in gold.periods
                    if p.end
                ),
                "unit_kept": f"単位:{gold.header.unit}" in text,
            }
    labels = Counter(normalize(row.label) for row in gold.rows)
    report["rows_ambiguous_without_hierarchy"] = sum(n for n in labels.values() if n > 1)
    return report


def _flat(row: list[str | None]) -> tuple:
    cells = [cell for cell in row if cell]
    amounts = [parse_amount(cell) for cell in cells]
    label = normalize("".join(cell for cell, a in zip(cells, amounts, strict=True) if a is None))
    return label, tuple(a for a in amounts if a is not None)
