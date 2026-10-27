"""Arbitration (design S6, section 6.4): every table ends in one explicit page state."""

from collections.abc import Sequence
from dataclasses import dataclass

from jpfs.checks import Check, derive_constraints, evaluate, uncovered_cells
from jpfs.model import UNIT_SCALES, PageState, Rounding, RoundingBasis, Table
from jpfs.text import label_defect


@dataclass(frozen=True, slots=True)
class Verification:
    rounding: Rounding
    rounding_basis: RoundingBasis
    checks: tuple[Check, ...]
    uncovered: tuple[tuple[int, int], ...]
    state: PageState
    reasons: tuple[str, ...]


def verify(
    table: Table,
    rounding: Rounding,
    rounding_basis: RoundingBasis,
    untrusted: Sequence[str] = (),
    warnings: Sequence[str] = (),
) -> Verification:
    """Check a table's constraints and decide its state.

    failed: no amount was bound to a period, so there is nothing to accept or review.
    needs_review: a constraint fails, a cell is vouched for by no check, printed content was not
    bound to a cell, a label looks damaged, the header is incomplete (no statement title, unit or
    dated period), or the text layer is untrusted. Facts without their statement are not correct
    facts, so a page whose title is neither printed nor inherited is reviewed.
    accepted_with_warnings: everything holds but something soft was noticed.
    verified: everything holds and nothing was noticed.
    """
    checks = evaluate(table, derive_constraints(table.rows), rounding)
    uncovered = uncovered_cells(table, checks)
    review = [
        *untrusted,
        *table.unplaced,
        *_failures(table, checks),
        *_unitless_decimals(table),
        *_damaged_labels(table),
    ]
    if uncovered:
        review.append(f"{len(uncovered)} cell(s) covered by no constraint")
    if table.header.title is None:
        review.append("no statement title on the page (continuation?): statement and scope unknown")
    if table.header.unit is None:
        review.append("unit not found on the page")
    if any(period.end is None for period in table.periods):
        review.append("value column without a dated period header")

    soft = [*warnings, *table.warnings]
    if rounding is Rounding.UNKNOWN:
        soft.append("rounding mode undetermined: checked against both truncation and rounding")

    if not any(cell for row in table.rows for cell in row.cells):
        state = PageState.FAILED
        review.insert(0, "no amount was bound to a period column")
    elif review:
        state = PageState.NEEDS_REVIEW
    elif soft:
        state = PageState.ACCEPTED_WITH_WARNINGS
    else:
        state = PageState.VERIFIED
    return Verification(rounding, rounding_basis, checks, uncovered, state, (*review, *soft))


def _damaged_labels(table: Table) -> list[str]:
    return [
        f"label '{row.label}' looks damaged: {defect}"
        for row in table.rows
        if (defect := label_defect(row.label))
    ]


def _unitless_decimals(table: Table) -> list[str]:
    """A decimal under 千円 or 百万円 is almost certainly a per-share figure whose 円 was not
    printed; it is flagged rather than given a unit by guesswork."""
    return [
        f"decimal amount '{cell.text}' under {unit}: its own unit is not printed"
        for row in table.rows
        if (unit := row.unit or table.header.unit) and UNIT_SCALES[unit] > 1
        for cell in row.cells
        if cell is not None and cell.amount.step < 1
    ]


def _failures(table: Table, checks: Sequence[Check]) -> list[str]:
    return [
        f"{c.constraint.name} fails for {table.periods[c.period].label} (residual {c.residual})"
        for c in checks
        if not c.passed
    ]
