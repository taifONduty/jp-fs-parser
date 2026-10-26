"""Cross-page assembly (design S4): a statement continued from an earlier page keeps its title.

Only the first table on a page can lack a title, because pages are split at statement titles. It
continues the statement that ends the previous page, provided the evidence agrees: the same dated
periods and the same unit. Untitled pages in between are followed back, so a statement running
over several pages is carried through; a page without tables ends the chain.
"""

from collections.abc import Callable, Sequence
from dataclasses import replace

from jpfs.model import Table

MAX_CONTINUATION = 4  # pages a statement may run on after the page with its title


def carry_over(
    tables: Sequence[Table], page: int, tables_on: Callable[[int], Sequence[Table]]
) -> tuple[Table, ...]:
    """The tables of a page, the untitled first one headed as the statement it continues."""
    if not tables or tables[0].header.title is not None:
        return tuple(tables)
    origin = _continued_statement(tables[0], page, tables_on)
    if origin is None:
        return tuple(tables)
    origin_page, statement = origin
    own = tables[0].header
    header = replace(
        own,
        title=statement.header.title,
        kind=statement.header.kind,
        consolidated=statement.header.consolidated,
        correction=own.correction or statement.header.correction,
        unit=own.unit or statement.header.unit,
        continued_from=origin_page,
    )
    return (replace(tables[0], header=header), *tables[1:])


def _continued_statement(
    continuation: Table, page: int, tables_on: Callable[[int], Sequence[Table]]
) -> tuple[int, Table] | None:
    for previous in range(page - 1, max(0, page - 1 - MAX_CONTINUATION), -1):
        tables = tables_on(previous)
        if not tables:
            return None
        last = tables[-1]
        if last.header.title is not None:
            return (previous, last) if _same_columns(continuation, last) else None
        if last.periods != continuation.periods:
            return None  # an unrelated untitled table breaks the chain
    return None


def _same_columns(continuation: Table, statement: Table) -> bool:
    periods_agree = bool(statement.periods) and continuation.periods == statement.periods
    dated = all(period.end is not None for period in statement.periods)
    units_agree = continuation.header.unit in (None, statement.header.unit)
    return periods_agree and dated and units_agree
