from datetime import date

import pytest

from jpfs.layout import INK, PageContent, Rule, Word, extract_tables, luminance
from jpfs.model import Amount, Period, Role, StatementKind

NOTES, PRIOR, CURRENT = 300.0, 420.0, 540.0  # right edges of the value columns
INDENT = 13.0


def _label(text: str, x0: float, top: float) -> Word:
    return Word(text, x0, top, x0 + 9 * len(text), top + 9)


def _figure(text: str, right: float, top: float) -> Word:
    return Word(text, right - 5 * len(text), top, right, top + 9)


def _line(top: float, label: str, prior: str, current: str, level: int = 0) -> list[Word]:
    return [
        _label(label, 60 + INDENT * level, top),
        _figure(prior, PRIOR, top),
        _figure(current, CURRENT, top),
    ]


def _body(top: float, rows: list[tuple[str, str, str, str | None]]) -> list[Word]:
    words = []
    for i, (label, prior, current, note) in enumerate(rows):
        words += _line(top + 12 * i, label, prior, current)
        if note:
            words.append(_figure(note, NOTES, top + 12 * i))
    return words


def _two_statement_page() -> PageContent:
    """An income statement with a 注記 column and 和暦 durations, then a second statement whose
    注記 header has no column under it."""
    words = [
        _label("（１）", 60, 40),
        _label("連結損益計算書", 90, 40),
        Word("（単位：百万円）", 470, 52, 540, 61),
        Word("注記", 285, 64, 300, 73),
        Word("前連結会計年度", 340, 64, 405, 73),
        Word("当連結会計年度", 460, 64, 525, 73),
        Word("(自令和6年4月1日至令和7年3月31日)", 320, 76, 418, 85),
        Word("(自令和7年4月1日至令和8年3月31日)", 440, 76, 538, 85),
        *_body(
            90,
            [
                ("売上高", "1,000", "1,200", "1"),
                ("売上原価", "600", "700", "2"),
                ("売上総利益", "400", "500", "3"),
                ("1株当たり当期純利益", "12.34", "15.67", None),
            ],
        ),
        _label("（２）連結包括利益計算書", 60, 140),
        Word("注記", 285, 152, 300, 161),
        Word("前連結会計年度", 340, 152, 405, 161),
        Word("当連結会計年度", 460, 152, 525, 161),
        *_body(
            166,
            [
                ("当期純利益", "400", "500", None),
                ("その他の包括利益", "10", "△20", None),
                ("包括利益", "410", "480", None),
            ],
        ),
        _figure("- 4 -", 305, 800),
    ]
    return PageContent(tuple(words), rules=(), width=600.0, text="")


def test_page_splits_into_statements_at_titles() -> None:
    income, comprehensive = extract_tables(_two_statement_page())

    assert income.header.title == "連結損益計算書"
    assert income.header.kind is StatementKind.INCOME_STATEMENT
    assert (income.header.unit, income.header.scale) == ("百万円", 1_000_000)
    assert income.periods == (
        Period("前連結会計年度", date(2025, 3, 31), start=date(2024, 4, 1)),
        Period("当連結会計年度", date(2026, 3, 31), start=date(2025, 4, 1)),
    )
    assert [row.label for row in income.rows][:3] == ["売上高", "売上原価", "売上総利益"]

    assert comprehensive.header.kind is StatementKind.COMPREHENSIVE_INCOME
    assert [p.label for p in comprehensive.periods] == ["前連結会計年度", "当連結会計年度"]
    assert comprehensive.rows[1].cells[1].amount == Amount(20, negative=True)


def test_figures_that_are_not_amounts_are_reported_not_glued_to_labels() -> None:
    income, _ = extract_tables(_two_statement_page())
    per_share = income.rows[-1]
    assert per_share.label == "1株当たり当期純利益"
    assert per_share.cells == (None, None)
    assert len(income.unplaced) == 2


def test_figures_in_a_non_period_column_become_note_references() -> None:
    income, _ = extract_tables(_two_statement_page())
    sales = income.rows[0]
    assert sales.notes == ("1",)
    assert [cell.amount.value for cell in sales.cells] == [1000, 1200]


def test_figures_under_a_header_that_names_no_period_are_reported_lost() -> None:
    words = [Word("年度中増減", 380, 64, 420, 73), Word("当期", 520, 64, 538, 73)]
    for i in range(3):
        words += _line(80 + 12 * i, f"項目{i}", "△5", "100")
    (table,) = extract_tables(PageContent(tuple(words), (), width=600.0, text=""))
    assert [period.label for period in table.periods] == ["当期"]
    assert len(table.unplaced) == 3
    assert all(not row.notes for row in table.rows)


def test_a_column_holds_every_figure_it_was_clustered_from() -> None:
    words = [Word("当期", 500, 64, 518, 73)]
    for i, right in enumerate((524.0, 531.0, 538.0)):  # ragged, each within tolerance of the next
        words += [_label(f"項目{i}", 60, 80 + 12 * i), _figure("100", right, 80 + 12 * i)]
    (table,) = extract_tables(PageContent(tuple(words), (), width=600.0, text=""))
    assert not table.unplaced
    assert all(row.cells[0] is not None for row in table.rows)


def test_rule_under_a_net_row_does_not_close_the_group_at_a_page_break() -> None:
    words = [
        Word("前連結会計年度", 340, 64, 405, 73),
        Word("当連結会計年度", 460, 64, 525, 73),
        _label("有形固定資産", 60, 88),
        *_line(100, "建物", "100", "90", level=1),
        *_line(112, "減価償却累計額", "△40", "△35", level=2),
        *_line(124, "建物（純額）", "60", "55", level=2),
        *_line(136, "建設仮勘定", "5", "6", level=1),  # the page breaks here
    ]
    rules = (Rule(300, 122.5, 545), Rule(300, 134.5, 545))  # above and below 建物（純額）
    (table,) = extract_tables(PageContent(tuple(words), rules, width=600.0, text=""))
    roles = {row.label: row.role for row in table.rows}
    assert roles["建物（純額）"] is Role.NET
    assert roles["建設仮勘定"] is Role.ITEM
    assert table.warnings == ("group '有形固定資産' has no closing total on this page",)


@pytest.mark.parametrize(
    ("colour", "visible"),
    [(None, True), ((0,), True), ((0.8, 0.933, 1), False), ((1,), False), ((0, 0, 0, 1), True)],
)
def test_rule_visibility_follows_luminance(colour: object, visible: bool) -> None:
    assert (luminance(colour) < INK) is visible
