"""Typed intermediate representation shared by every pipeline stage.

All objects are immutable; a stage that refines a table returns a new one.
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

BBox = tuple[float, float, float, float]  # x0, top, x1, bottom in PDF points


class Role(StrEnum):
    SECTION = "section"  # heading without values (資産の部, 流動資産)
    ITEM = "item"
    GROSS = "gross"  # carries values and opens a gross-to-net group
    CONTRA = "contra"  # negative member, e.g. 減価償却累計額
    NET = "net"  # closes a gross group (純額)
    TOTAL = "total"  # closes a run of members (合計, 小計)


class StatementKind(StrEnum):
    BALANCE_SHEET = "balance_sheet"
    INCOME_STATEMENT = "income_statement"
    COMPREHENSIVE_INCOME = "comprehensive_income"
    CHANGES_IN_EQUITY = "changes_in_equity"
    CASH_FLOWS = "cash_flows"


class Rounding(StrEnum):
    TRUNCATE = "truncate"  # 切り捨て
    ROUND = "round"  # 四捨五入
    UNKNOWN = "unknown"  # either; checks use the hull of both intervals


class PageState(StrEnum):
    VERIFIED = "verified"
    ACCEPTED_WITH_WARNINGS = "accepted_with_warnings"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Amount:
    """A printed amount in display units.

    '－' is nil (the line exists with no balance); a blank cell is not an Amount at all.
    '△0' keeps its sign: a negative amount smaller than one display unit.
    """

    magnitude: int
    negative: bool = False
    nil: bool = False

    @property
    def value(self) -> int:
        return -self.magnitude if self.negative else self.magnitude


@dataclass(frozen=True, slots=True)
class Cell:
    amount: Amount
    text: str
    bbox: BBox
    corrected: bool = False  # 訂正箇所: underlined in a 訂正後 filing


@dataclass(frozen=True, slots=True)
class Period:
    label: str
    end: date | None
    start: date | None = None  # set for durations (自…至…)


@dataclass(frozen=True, slots=True)
class Row:
    label: str  # as printed
    bbox: BBox
    cells: tuple[Cell | None, ...]  # aligned with Table.periods; None is a blank cell
    level: int = 0
    notes: tuple[str, ...] = ()  # footnote markers such as ※1
    rule_above: bool = False
    parent: int | None = None
    children: tuple[int, ...] = ()
    role: Role = Role.ITEM
    path: tuple[str, ...] = ()  # normalised labels from the root; the row's identity


@dataclass(frozen=True, slots=True)
class Header:
    title: str | None
    kind: StatementKind | None
    consolidated: bool | None
    correction: str | None  # "before" / "after" for 訂正前 / 訂正後 filings
    unit: str | None
    scale: int | None


@dataclass(frozen=True, slots=True)
class Table:
    header: Header
    periods: tuple[Period, ...]
    rows: tuple[Row, ...]
    unplaced: tuple[str, ...] = ()  # printed content not bound to a cell: each is a lost fact
    warnings: tuple[str, ...] = ()
