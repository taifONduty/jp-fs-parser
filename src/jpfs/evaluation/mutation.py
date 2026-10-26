"""How much does "all checks pass" guarantee? Inject one realistic error at a time into a correct
table and count how often at least one constraint fails."""

from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import replace
from decimal import Decimal

from jpfs.checks import derive_constraints, evaluate
from jpfs.model import Amount, Cell, Rounding, Table

OCR_CONFUSIONS = {
    "0": "689", "1": "7", "2": "7", "3": "8", "4": "9",
    "5": "6", "6": "508", "7": "1", "8": "3609", "9": "08",
}  # fmt: skip

Mutant = tuple[tuple[str, ...], Table]


def detection_rates(table: Table, rounding: Rounding) -> dict[str, dict]:
    constraints = derive_constraints(table.rows)
    if not all(check.passed for check in evaluate(table, constraints, rounding)):
        raise ValueError("mutation testing needs a table whose checks all pass")
    detected: Counter[str] = Counter()
    total: Counter[str] = Counter()
    for categories, mutant in _mutants(table):
        caught = not all(check.passed for check in evaluate(mutant, constraints, rounding))
        for category in categories:
            total[category] += 1
            detected[category] += caught
    return {
        category: {
            "detected": detected[category],
            "total": n,
            "rate": round(detected[category] / n, 3),
        }
        for category, n in total.items()
    }


def _mutants(table: Table) -> Iterator[Mutant]:
    for r, row in enumerate(table.rows):
        for p, cell in enumerate(row.cells):
            if cell is not None and not cell.amount.nil:
                for categories, amount in _amount_errors(cell.amount):
                    yield categories, _with(table, {(r, p): replace(cell, amount=amount)})
    yield from _swaps(table)


def _amount_errors(amount: Amount) -> Iterator[tuple[tuple[str, ...], Amount]]:
    """Single-character errors on the printed digits; 'units digit' is the last printed one."""
    text = str(amount.magnitude)
    places = [i for i, ch in enumerate(text) if ch.isdigit()]
    for i in places:
        original = text[i]
        place = "units digit" if i == places[-1] else "tens digit or above"
        for digit in "0123456789":
            if digit == original or (i == places[0] and digit == "0" and len(places) > 1):
                continue
            categories = ("any digit", place)
            if digit in OCR_CONFUSIONS[original]:
                categories += ("OCR-confusable digit",)
            yield categories, replace(amount, magnitude=Decimal(text[:i] + digit + text[i + 1 :]))
        if len(places) > 1:
            yield ("dropped digit",), replace(amount, magnitude=Decimal(text[:i] + text[i + 1 :]))
    if amount.negative and amount.magnitude:
        yield ("lost △",), replace(amount, negative=False)


def _swaps(table: Table) -> Iterator[Mutant]:
    rows = table.rows
    for r, row in enumerate(rows):
        for p, cell in enumerate(row.cells):
            below = rows[r + 1].cells[p] if r + 1 < len(rows) else None
            if cell and below and cell.amount != below.amount:
                yield ("adjacent rows swapped",), _with(table, {(r, p): below, (r + 1, p): cell})
            beside = row.cells[p + 1] if p + 1 < len(row.cells) else None
            if cell and beside and cell.amount != beside.amount:
                yield ("period columns swapped",), _with(table, {(r, p): beside, (r, p + 1): cell})


def _with(table: Table, changes: Mapping[tuple[int, int], Cell]) -> Table:
    rows = tuple(
        replace(row, cells=tuple(changes.get((r, p), cell) for p, cell in enumerate(row.cells)))
        if any(key[0] == r for key in changes)
        else row
        for r, row in enumerate(table.rows)
    )
    return replace(table, rows=rows)
