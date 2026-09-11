"""Tests for the Duration value type: four ladders, arithmetic, normalization.

The governing rule, and the reason this type is not just an int of seconds:
the four ladders never convert into each other.  `24h` is not `1d`, because
`d` means "same wall-clock time, next day" and that is 23, 24 or 25 hours
depending on where it lands.
"""

from __future__ import annotations

import pytest

from dtcalc.duration import Duration
from dtcalc.errors import DtcalcError

D = Duration.build


# --------------------------------------------------------------------------
# 1.1  construction and arithmetic
# --------------------------------------------------------------------------


def test_build_accumulates_within_a_ladder() -> None:
    assert D(h=1, m=30) == D(ms=5_400_000)
    assert D(w=1, d=1) == D(d=8)
    assert D(y=1, mo=3) == D(mo=15)


def test_build_keeps_ladders_separate() -> None:
    d = D(w=3, h=2, m=5)
    assert d.days == 21
    assert d.millis == 7_500_000
    assert d.months == 0
    assert d.bdays == 0


def test_build_accepts_fractional_exact_units() -> None:
    assert D(s=1.5) == D(ms=1500)
    assert D(h=0.5) == D(m=30)


def test_build_rejects_fractional_calendar_units() -> None:
    with pytest.raises(DtcalcError, match="whole number"):
        D(mo=1.5)


def test_build_rejects_business_days_mixed_with_calendar_units() -> None:
    with pytest.raises(DtcalcError, match="business days"):
        D(bd=1, d=1)
    with pytest.raises(DtcalcError, match="business days"):
        D(bd=1, mo=1)


def test_business_days_may_carry_an_exact_part() -> None:
    d = D(bd=3, h=2)
    assert (d.bdays, d.millis) == (3, 7_200_000)


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (D(h=3), D(m=45), D(h=3, m=45)),
        (D(d=1), D(h=2), D(d=1, h=2)),
        (D(mo=1), D(d=3), D(mo=1, d=3)),
        (D(bd=1), D(h=2), D(bd=1, h=2)),
        (D(h=1), D(h=-1), D()),
    ],
)
def test_addition(left: Duration, right: Duration, expected: Duration) -> None:
    assert left + right == expected


def test_addition_across_the_business_day_boundary_is_an_error() -> None:
    with pytest.raises(DtcalcError, match="business days"):
        _ = D(bd=1) + D(d=1)


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (D(h=3), D(m=45), D(h=2, m=15)),
        (D(d=1), D(m=90), D(d=1, m=-90)),
        (D(w=2), D(d=3), D(d=11)),
    ],
)
def test_subtraction(left: Duration, right: Duration, expected: Duration) -> None:
    assert left - right == expected


def test_negation_flips_every_ladder() -> None:
    assert -D(mo=1, d=2, h=3) == D(mo=-1, d=-2, h=-3)


@pytest.mark.parametrize(
    ("duration", "factor", "expected"),
    [
        (D(h=3), 5.0, D(h=15)),
        (D(h=8), 3.0, D(h=24)),
        (D(m=15), 4.0, D(h=1)),
        (D(d=2), 3.0, D(d=6)),
        (D(mo=2), 6.0, D(y=1)),
        (D(bd=3), 2.0, D(bd=6)),
        (D(h=1), 0.5, D(m=30)),
        (D(h=1), -2.0, D(h=-2)),
    ],
)
def test_scalar_multiplication(duration: Duration, factor: float, expected: Duration) -> None:
    assert duration * factor == expected


def test_multiplication_of_a_calendar_part_by_a_fraction_is_an_error() -> None:
    with pytest.raises(DtcalcError, match="whole number"):
        _ = D(mo=1) * 1.5


@pytest.mark.parametrize(
    ("duration", "divisor", "expected"),
    [
        (D(h=24), 4.0, D(h=6)),
        (D(mo=12), 2.0, D(mo=6)),
        (D(h=1), 2.0, D(m=30)),
    ],
)
def test_scalar_division(duration: Duration, divisor: float, expected: Duration) -> None:
    assert duration / divisor == expected


def test_dividing_a_calendar_part_unevenly_is_an_error() -> None:
    """`1d / 4` cannot be `6h`: a day is not always 24 hours."""
    with pytest.raises(DtcalcError, match="evenly"):
        _ = D(d=1) / 4.0


def test_division_by_zero_is_an_error() -> None:
    with pytest.raises(DtcalcError, match="zero"):
        _ = D(h=1) / 0.0


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (D(h=2), D(m=15), 8.0),
        (D(w=2), D(d=7), 2.0),
        (D(y=1), D(mo=3), 4.0),
        (D(bd=6), D(bd=2), 3.0),
    ],
)
def test_duration_divided_by_duration_is_a_number(
    left: Duration, right: Duration, expected: float
) -> None:
    assert left.divide_by(right) == expected


def test_duration_division_across_ladders_is_an_error() -> None:
    with pytest.raises(DtcalcError, match="same"):
        D(d=1).divide_by(D(h=5))


def test_division_by_a_zero_duration_is_an_error() -> None:
    with pytest.raises(DtcalcError, match="zero"):
        D(h=1).divide_by(D())


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (D(m=97), D(m=15), D(m=7)),
        (D(d=10), D(d=3), D(d=1)),
        (D(mo=14), D(y=1), D(mo=2)),
    ],
)
def test_modulo_within_a_ladder(left: Duration, right: Duration, expected: Duration) -> None:
    assert left % right == expected


def test_modulo_across_ladders_is_an_error() -> None:
    """Stricter than comparison: a wrong modulo result would be silent."""
    with pytest.raises(DtcalcError, match="same"):
        _ = D(d=1) % D(h=5)


def test_modulo_by_zero_is_an_error() -> None:
    with pytest.raises(DtcalcError, match="zero"):
        _ = D(h=1) % D()


# --------------------------------------------------------------------------
# 1.2  normalization and formatting
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        (D(), "0s"),
        (D(m=90), "1h30m"),
        (D(s=3661), "1h1m1s"),
        (D(h=24), "24h"),  # never 1d
        (D(h=15), "15h"),
        (D(h=168), "168h"),
        (D(d=8), "1w1d"),
        (D(d=7), "1w"),
        (D(mo=15), "1y3mo"),
        (D(mo=12), "1y"),
        (D(w=3, h=2, m=5), "3w2h5m"),
        (D(bd=3), "3bd"),
        (D(bd=1, h=2), "1bd2h"),
        (D(s=1.5), "1.5s"),
        (D(ms=250), "250ms"),
        (D(ms=1), "1ms"),
        (D(m=1, s=1.5), "1m1.5s"),
        (D(h=-1, m=-30), "-1h30m"),
        (D(d=-8), "-1w1d"),
        (D(mo=1, d=3, h=4), "1mo3d4h"),
        (D(y=1, mo=2, w=1, d=1, h=1, m=1, s=1), "1y2mo1w1d1h1m1s"),
    ],
)
def test_formatting(duration: Duration, expected: str) -> None:
    assert str(duration) == expected


def test_mixed_sign_ladders_print_each_with_its_own_sign() -> None:
    assert str(D(d=1) - D(m=90)) == "1d -1h30m"
    assert str(D(d=-1) + D(m=90)) == "-1d 1h30m"


@pytest.mark.parametrize(
    "duration",
    [D(), D(m=90), D(d=8), D(mo=15), D(w=3, h=2, m=5), D(d=1, m=-90), D(bd=1, h=2), D(ms=250)],
)
def test_normalization_is_idempotent(duration: Duration) -> None:
    once = duration.normalized()
    assert once == once.normalized()
    assert str(once) == str(once.normalized())


def test_normalization_does_not_change_the_value() -> None:
    assert D(m=90).normalized() == D(m=90)


# --------------------------------------------------------------------------
# 1.3  cross-ladder comparison policy
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (D(h=1), D(h=2), -1),
        (D(h=2), D(h=1), 1),
        (D(h=1), D(m=60), 0),
        (D(y=1), D(mo=13), -1),  # months-only, comparable despite differing units
        (D(mo=1, d=1), D(mo=1), 1),  # difference is sign-determinate
        (D(d=1), D(h=25), -1),  # nominal 24h day
        (D(d=1), D(h=24), 0),  # nominal equality
        (D(w=1), D(h=169), -1),
        (D(bd=1), D(bd=2), -1),
        (D(bd=1, h=1), D(bd=1), 1),
    ],
)
def test_comparison(left: Duration, right: Duration, expected: int) -> None:
    assert left.compare(right) == expected
    assert right.compare(left) == -expected


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (D(mo=1), D(d=30)),
        (D(y=1), D(h=8760)),
        (D(bd=1), D(d=1)),
        (D(bd=1), D(h=24)),
        (D(mo=1), D(bd=1)),
    ],
)
def test_incomparable_pairs_error(left: Duration, right: Duration) -> None:
    with pytest.raises(DtcalcError, match="compare"):
        left.compare(right)


def test_structural_equality_is_distinct_from_language_equality() -> None:
    """`1d == 24h` is true in the language, but they are not the same value."""
    assert D(d=1) != D(h=24)
    assert D(d=1).compare(D(h=24)) == 0


# --------------------------------------------------------------------------
# 1.3a  numeric precision and division results
# --------------------------------------------------------------------------


def test_duration_division_truncates_toward_zero_at_millisecond_resolution() -> None:
    assert D(h=1) / 7.0 == D(ms=514_285)
    assert str(D(h=1) / 7.0) == "8m34.285s"


def test_truncation_is_toward_zero_for_negatives() -> None:
    assert D(h=-1) / 7.0 == D(ms=-514_285)


def test_ladder_predicates() -> None:
    assert D(h=1).ladders == frozenset({"exact"})
    assert D(d=1).ladders == frozenset({"caldays"})
    assert D(mo=1).ladders == frozenset({"calmonths"})
    assert D(bd=1).ladders == frozenset({"bdays"})
    assert D(w=3, h=2).ladders == frozenset({"caldays", "exact"})
    assert D().ladders == frozenset()


def test_modulo_truncates_rather_than_floors_so_negatives_keep_their_sign() -> None:
    assert D(m=-97) % D(m=15) == D(m=-7)


def test_multiplying_by_zero_gives_the_zero_duration() -> None:
    assert D(w=3, h=2) * 0.0 == D()
    assert str(D(w=3, h=2) * 0.0) == "0s"


def test_zero_duration_divided_by_a_duration_is_zero() -> None:
    assert D().divide_by(D(h=1)) == 0.0


def test_sole_component_reports_the_single_ladders_magnitude() -> None:
    assert D(h=2).sole_component() == 7_200_000
    assert D(d=3).sole_component() == 3
    assert D(mo=5).sole_component() == 5


def test_single_ladder_sharing() -> None:
    assert D(h=2).shares_a_single_ladder_with(D(m=15))
    assert not D(d=1).shares_a_single_ladder_with(D(h=5))
    assert not D(d=1, h=1).shares_a_single_ladder_with(D(h=5))


def test_calendar_division_messages_are_not_written_in_broken_english() -> None:
    with pytest.raises(DtcalcError, match="1 month does not divide evenly"):
        _ = D(mo=1) / 4.0
    with pytest.raises(DtcalcError, match="5 months does not divide evenly"):
        _ = D(mo=5) / 4.0
