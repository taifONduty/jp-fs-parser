import pytest

from jpfs.checks import Interval, interval
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
