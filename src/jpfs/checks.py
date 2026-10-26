"""Accounting constraints derived from a table's own tree, checked with interval arithmetic.

A printed amount stands for the interval of true values it could have been rounded from, as in
XBRL Calculations 1.1, and a constraint holds when the interval of the printed total overlaps the
interval sum of its terms. The tolerance therefore follows from the number of terms and the
rounding mode rather than from a chosen epsilon.
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from itertools import chain
from math import comb

from jpfs.model import Amount, Role, Rounding, Row, Table

TRUNCATION_ALPHA = 0.01  # significance of the sign test that infers truncation


@dataclass(frozen=True, slots=True)
class Interval:
    lo: float
    hi: float
    lo_closed: bool = True
    hi_closed: bool = True

    def __add__(self, other: "Interval") -> "Interval":
        return Interval(
            self.lo + other.lo,
            self.hi + other.hi,
            self.lo_closed and other.lo_closed,
            self.hi_closed and other.hi_closed,
        )

    def __contains__(self, x: float) -> bool:
        above = self.lo < x or (self.lo == x and self.lo_closed)
        below = x < self.hi or (x == self.hi and self.hi_closed)
        return above and below

    def overlaps(self, other: "Interval") -> bool:
        lo, hi = max(self.lo, other.lo), min(self.hi, other.hi)
        return lo < hi or (lo == hi and lo in self and lo in other)

    def hull(self, other: "Interval") -> "Interval":
        first = min(self, other, key=lambda i: (i.lo, not i.lo_closed))
        last = max(self, other, key=lambda i: (i.hi, i.hi_closed))
        return Interval(first.lo, last.hi, first.lo_closed, last.hi_closed)

    def scaled(self, factor: int) -> "Interval":
        return Interval(self.lo * factor, self.hi * factor, self.lo_closed, self.hi_closed)


ZERO = Interval(0, 0)


def interval(amount: Amount, rounding: Rounding) -> Interval:
    """True values, in display units, consistent with a printed amount."""
    if amount.nil:
        return ZERO
    if rounding is Rounding.UNKNOWN:
        return interval(amount, Rounding.TRUNCATE).hull(interval(amount, Rounding.ROUND))
    m = amount.magnitude
    if rounding is Rounding.TRUNCATE:
        lo, hi, lo_closed, hi_closed = m, m + 1, True, False
    else:
        lo, hi, lo_closed, hi_closed = max(m - 0.5, 0), m + 0.5, True, True
    if not amount.negative:
        return Interval(lo, hi, lo_closed, hi_closed)
    return Interval(-hi, -lo, hi_closed, lo_closed and m > 0)  # △0 is strictly negative


@dataclass(frozen=True, slots=True)
class Constraint:
    total: int  # row index of the closing row
    terms: tuple[int, ...]  # row indices whose values sum to it
    name: str


@dataclass(frozen=True, slots=True)
class Check:
    constraint: Constraint
    period: int
    passed: bool
    residual: int  # printed total minus the printed sum of its terms


def derive_constraints(rows: Sequence[Row]) -> tuple[Constraint, ...]:
    """One constraint per closing row: a total sums the members before it, back to and including
    the previous total of the same group (so 小計 chains work); a net adds its contras to the gross.
    A member is a leaf row, or a sub-group through its own closing row."""
    roots = tuple(i for i, row in enumerate(rows) if row.parent is None)
    constraints = []
    for i, row in enumerate(rows):
        if row.role not in (Role.TOTAL, Role.NET):
            continue
        siblings = rows[row.parent].children if row.parent is not None else roots
        before = siblings[: siblings.index(i)]
        start = max((k for k, j in enumerate(before) if rows[j].role is Role.TOTAL), default=0)
        contributions = [_contribution(rows, j) for j in before[start:]]
        if None in contributions:
            continue
        gross = (row.parent,) if row.role is Role.NET else ()
        terms = gross + tuple(chain.from_iterable(contributions))
        if terms:
            kind = "net" if row.role is Role.NET else "sum"
            constraints.append(Constraint(i, terms, f"{kind}:{row.path[-1]}"))
    return tuple(constraints)


def _contribution(rows: Sequence[Row], i: int) -> tuple[int, ...] | None:
    """Rows a member adds to its group's total; None when a sub-group has no closing row."""
    row = rows[i]
    if row.children:
        closing = row.children[-1]
        return (closing,) if rows[closing].role in (Role.TOTAL, Role.NET) else None
    return (i,) if any(row.cells) else ()


def evaluate(
    table: Table, constraints: Sequence[Constraint], rounding: Rounding
) -> tuple[Check, ...]:
    """Check every constraint in every period whose total is printed; blank terms count as zero."""
    return tuple(
        Check(constraint, period, span.overlaps(interval(total, rounding)), total.value - printed)
        for constraint in constraints
        for period, total, span, printed in _sums(table, constraint, rounding)
    )


def _sums(
    table: Table, constraint: Constraint, rounding: Rounding
) -> Iterator[tuple[int, Amount, Interval, int]]:
    """Per period with a printed total: the total, the interval sum and printed sum of its terms."""
    for period in range(len(table.periods)):
        total = table.rows[constraint.total].cells[period]
        if total is None:
            continue
        terms = (table.rows[t].cells[period] for t in constraint.terms)
        amounts = [cell.amount for cell in terms if cell is not None]
        span = sum((interval(a, rounding) for a in amounts), start=ZERO)
        yield period, total.amount, span, sum(a.value for a in amounts)


def infer_rounding(tables: Sequence[Table]) -> Rounding:
    """Sign test on the residuals (printed total minus printed sum) of a document's constraints.

    Under rounding a residual is symmetric about zero, so when exactly one of r and -r fits the
    truncation interval, the fitting one is the observed one half of the time. Under truncation
    it always is. Finding almost no misfits among those informative residuals is therefore
    evidence for truncation. Without that evidence the mode stays unknown, which is safer than
    picking whichever mode passes: that would let a real error hide in the slack.
    """
    informative = misfits = 0
    for table in tables:
        for constraint in derive_constraints(table.rows):
            for _, total, span, printed in _sums(table, constraint, Rounding.TRUNCATE):
                fits = span.overlaps(interval(total, Rounding.TRUNCATE))
                mirror = Amount(abs(2 * printed - total.value), negative=2 * printed < total.value)
                if fits != span.overlaps(interval(mirror, Rounding.TRUNCATE)):
                    informative += 1
                    misfits += not fits
    p_value = sum(comb(informative, k) for k in range(misfits + 1)) / 2**informative
    return Rounding.TRUNCATE if p_value < TRUNCATION_ALPHA else Rounding.UNKNOWN


def uncovered_cells(table: Table, checks: Sequence[Check]) -> tuple[tuple[int, int], ...]:
    """(row, period) cells that no check touches: nothing vouches for them."""
    covered = {
        (row, check.period)
        for check in checks
        for row in (check.constraint.total, *check.constraint.terms)
    }
    return tuple(
        (r, p)
        for r, row in enumerate(table.rows)
        for p, cell in enumerate(row.cells)
        if cell is not None and (r, p) not in covered
    )
