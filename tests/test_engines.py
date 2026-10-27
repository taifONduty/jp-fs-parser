from datetime import date

import pytest

from jpfs.engines import parser_for
from jpfs.engines.grid import Grid, GridCell, grounded, parse_html_table, to_table
from jpfs.pipeline import parse_pdf


def _row(label: str, x0: float | None, *values: str) -> tuple[GridCell, ...]:
    return (GridCell(label, x0), *(GridCell(v) for v in values))


def test_html_table_rows_repeat_spanned_cells() -> None:
    html = (
        "<table><tr><th colspan='2'>前期</th><th>当期</th></tr>"
        "<tr><td>現金</td><td>1</td></tr></table>"
    )
    assert parse_html_table(html) == [["前期", "前期", "当期"], ["現金", "1"]]


def test_grid_becomes_a_tree_with_periods_notes_and_header() -> None:
    grid = Grid(
        (
            _row(
                "", None, "注記", "前連結会計年度(2025年3月31日)", "当連結会計年度(2026年3月31日)"
            ),
            _row("資産の部", 60.0, "", "", ""),
            _row("流動資産", 73.0, "", "", ""),
            _row("現金及び預金", 86.0, "※1", "1,000", "1,200"),
            _row("売掛金", 86.0, "", "500", "△20"),
            _row("流動資産合計", 86.0, "", "1,500", "1,180"),
        ),
        context="（１）連結貸借対照表\n（単位：百万円）",
    )
    table = to_table(grid, page_text="")
    assert table is not None
    assert (table.header.title, table.header.unit, table.header.consolidated) == (
        "連結貸借対照表",
        "百万円",
        True,
    )
    assert [p.end for p in table.periods] == [date(2025, 3, 31), date(2026, 3, 31)]
    cash, receivables, total = table.rows[2:]
    assert cash.path == ("資産の部", "流動資産", "現金及び預金")
    assert cash.notes == ("※1",)
    assert receivables.cells[1].amount.value == -20
    assert total.parent == 1


def test_model_rows_take_indentation_from_their_text_layer_line() -> None:
    words = [
        {"text": "流動資産", "x0": 73.0, "top": 100.0},
        {"text": "現金及び預金", "x0": 86.0, "top": 112.0},
        {"text": "1,000", "x0": 400.0, "top": 112.0},
        {"text": "1,200", "x0": 500.0, "top": 112.0},
    ]
    rows = grounded([["流動資産", "", ""], ["現金及び預金", "1,000", "1,200"]], words)
    assert [row[0].x0 for row in rows] == [73.0, 86.0]
    assert rows[1][1] == GridCell("1,000")


def test_engines_are_chosen_by_name() -> None:
    assert parser_for("geometry") is parse_pdf
    with pytest.raises(ValueError, match="unknown engine"):
        parser_for("tesseract")
