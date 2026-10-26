import pytest

from jpfs.checks import Check, Constraint, Interval, infer_rounding, interval
from jpfs.model import Amount, Rounding


@pytest.mark.parametrize(
    ("amount", "rounding", "expected"),
    [
        (Amount(5), Rounding.TRUNCATE, Interval(5, 6, True, False)),
        (Amount(5, negative=True), Rounding.TRUNCATE, Interval(-6, -5, False, True)),
        (Amount(0, negative=True), Rounding.TRUNCATE, Interval(-1, 0, False, False)),
        (Amount(5), Rounding.ROUND, Interval(4.5, 5.5)),
        (Amount(0, negative=True), Rounding.ROUND, Interval(-0.5, 0, True, False)),
        (Amount(5), Rounding.UNKNOWN, Interval(4.5, 6, True, False)),
        (Amount(0, nil=True), Rounding.TRUNCATE, Interval(0, 0)),
    ],
)
def test_interval_of_printed_amount(amount: Amount, rounding: Rounding, expected: Interval) -> None:
    assert interval(amount, rounding) == expected


def test_overlap_respects_open_bounds() -> None:
    assert not Interval(0, 1, True, False).overlaps(Interval(1, 2))
    assert Interval(0, 1).overlaps(Interval(1, 2))
    assert Interval(0, 0).overlaps(Interval(0, 1, True, False))  # "0" total over nil terms


def _checks(*outcomes: tuple[int, bool]) -> list[Check]:
    constraint = Constraint(total=0, terms=(), name="sum:x")
    return [Check(constraint, 0, passed, residual) for residual, passed in outcomes]


def test_sign_test_infers_truncation_from_one_sided_residuals() -> None:
    assert infer_rounding(_checks(*[(1, True)] * 7)) is Rounding.TRUNCATE
    assert infer_rounding(_checks(*[(1, True)] * 12, (-1, False))) is Rounding.TRUNCATE


def test_sign_test_abstains_without_evidence() -> None:
    assert infer_rounding(_checks(*[(0, True)] * 20)) is Rounding.UNKNOWN
    assert infer_rounding(_checks(*[(1, True)] * 4, *[(-1, False)] * 4)) is Rounding.UNKNOWN
