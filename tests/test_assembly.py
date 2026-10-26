from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import date

import pytest

from jpfs.assembly import MAX_CONTINUATION, carry_over
from jpfs.model import Header, Period, StatementKind, Table

PERIODS = (Period("前連結会計年度", date(2024, 3, 31)), Period("当連結会計年度", date(2025, 3, 31)))
STATEMENT = Table(
    Header("連結貸借対照表", StatementKind.BALANCE_SHEET, True, None, "百万円"), PERIODS, rows=()
)
CONTINUATION = Table(Header(None, None, None, None, "百万円"), PERIODS, rows=())
UNRELATED = Table(Header(None, None, None, None, "百万円"), PERIODS[:1], rows=())


def _document(*pages: Sequence[Table]) -> Callable[[int], Sequence[Table]]:
    return lambda number: pages[number - 1]


def test_a_continuation_inherits_the_statement_it_continues_across_pages() -> None:
    document = _document((STATEMENT,), (CONTINUATION,), (CONTINUATION,))
    (table,) = carry_over((CONTINUATION,), 3, document)
    header = table.header
    assert (header.title, header.kind, header.consolidated) == (
        "連結貸借対照表",
        StatementKind.BALANCE_SHEET,
        True,
    )
    assert header.continued_from == 1


@pytest.mark.parametrize(
    "earlier",
    [
        [()],  # a page without tables ends the chain
        [(replace(STATEMENT, periods=PERIODS[:1]),)],  # other columns
        [(replace(STATEMENT, header=replace(STATEMENT.header, unit="千円")),)],  # other unit
        [(STATEMENT,), (UNRELATED,)],  # an unrelated untitled table in between
    ],
)
def test_no_title_is_inherited_without_agreeing_evidence(earlier: list[tuple[Table, ...]]) -> None:
    document = _document(*earlier, (CONTINUATION,))
    (table,) = carry_over((CONTINUATION,), len(earlier) + 1, document)
    assert table.header.title is None


def test_the_chain_ends_after_the_longest_continuation() -> None:
    pages = [(STATEMENT,), *[(CONTINUATION,)] * (MAX_CONTINUATION + 1)]
    (table,) = carry_over((CONTINUATION,), len(pages), _document(*pages))
    assert table.header.title is None
