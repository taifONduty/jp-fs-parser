"""Arbitration (design S6, section 6.4): every table ends in one explicit page state."""

from collections.abc import Sequence
from dataclasses import dataclass

from jpfs.checks import Check, derive_constraints, evaluate, uncovered_cells
from jpfs.model import PageState, Rounding, Table


@dataclass(frozen=True, slots=True)
class Verification:
    rounding: Rounding
    rounding_basis: str  # declared | inferred | undetermined
    checks: tuple[Check, ...]
    uncovered: tuple[tuple[int, int], ...]
    state: PageState
    reasons: tuple[str, ...]


def verify(
    table: Table,
    rounding: Rounding,
    rounding_basis: str,
    untrusted: Sequence[str] = (),
    warnings: Sequence[str] = (),
) -> Verification:
    """Check a table's constraints and decide its state.

    needs_review: a constraint fails, a cell is vouched for by no check, printed content was not
    bound to a cell, the header is incomplete, or the text layer is untrusted.
    accepted_with_warnings: everything holds but something soft was noticed.
    verified: everything holds and nothing was noticed.
    """
    checks = evaluate(table, derive_constraints(table.rows), rounding)
    uncovered = uncovered_cells(table, checks)
    review = [*untrusted, *table.unplaced, *_failures(table, checks)]
    if uncovered:
        review.append(f"{len(uncovered)} cell(s) covered by no constraint")
    if table.header.unit is None:
        review.append("unit not found on the page")
    if any(period.end is None for period in table.periods):
        review.append("value column without a dated period header")

    soft = [*warnings, *table.warnings]
    if rounding is Rounding.UNKNOWN:
        soft.append("rounding mode undetermined: checked against both truncation and rounding")

    if review:
        state = PageState.NEEDS_REVIEW
    elif soft:
        state = PageState.ACCEPTED_WITH_WARNINGS
    else:
        state = PageState.VERIFIED
    return Verification(rounding, rounding_basis, checks, uncovered, state, (*review, *soft))


def _failures(table: Table, checks: Sequence[Check]) -> list[str]:
    return [
        f"{c.constraint.name} fails for {table.periods[c.period].label} (residual {c.residual})"
        for c in checks
        if not c.passed
    ]
