"""Tests for the builtin functions."""

from __future__ import annotations

import pytest

from dtcalc.clock import FixedClock
from dtcalc.date import Date
from dtcalc.duration import Duration
from dtcalc.env import Env
from dtcalc.errors import DtcalcError
from dtcalc.evaluator import evaluate_line
from dtcalc.instant import Instant
from dtcalc.values import Boolean, Number

from .support import NY, TEST_NOW

D = Duration.build

# The frozen clock reads 2026-05-23T12:15:13 in New York, a Saturday.
FROZEN_EPOCH = 1779552913.0


@pytest.fixture
def env() -> Env:
    return Env(clock=FixedClock(TEST_NOW), zone=NY)


def ev(env: Env, source: str) -> object:
    return evaluate_line(source, env)


def wall(env: Env, source: str) -> str:
    value = ev(env, source)
    assert isinstance(value, Instant)
    return value.wall_clock().isoformat()


def date_of(env: Env, source: str) -> str:
    value = ev(env, source)
    assert isinstance(value, Date), f"{source} gave {value!r}"
    return str(value)


def dur(env: Env, source: str) -> str:
    value = ev(env, source)
    assert isinstance(value, Duration)
    return str(value)


# --------------------------------------------------------------------------
# 6.1  min / max
# --------------------------------------------------------------------------


def test_min_and_max_over_instants(env: Env) -> None:
    ev(env, "a = now")
    ev(env, "b = now + 5h")
    ev(env, "c = now - 2h")
    assert wall(env, "min(a, b, c)") == "2026-05-23T10:15:13"
    assert wall(env, "max(a, b, c)") == "2026-05-23T17:15:13"


def test_min_and_max_over_durations(env: Env) -> None:
    assert dur(env, "min(3h, 45m, 2h)") == "45m"
    assert dur(env, "max(3h, 45m, 2h)") == "3h"


def test_min_and_max_over_numbers(env: Env) -> None:
    assert ev(env, "min(3, 1, 2)") == Number(1.0)
    assert ev(env, "max(3, 1, 2)") == Number(3.0)


def test_a_single_argument_is_allowed(env: Env) -> None:
    assert dur(env, "min(3h)") == "3h"


def test_min_uses_the_nominal_day_when_comparing_ladders(env: Env) -> None:
    assert dur(env, "min(1d, 25h)") == "1d"


def test_mixed_argument_types_are_an_error(env: Env) -> None:
    with pytest.raises(DtcalcError, match="same kind"):
        ev(env, "min(now, 3h)")


def test_incomparable_durations_are_an_error(env: Env) -> None:
    with pytest.raises(DtcalcError, match="compare"):
        ev(env, "min(1mo, 720h)")


# --------------------------------------------------------------------------
# 6.1  round / trunc / ceil on instants
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("trunc(now, 1h)", "2026-05-23T12:00:00"),
        ("round(now, 1h)", "2026-05-23T12:00:00"),
        ("ceil(now, 1h)", "2026-05-23T13:00:00"),
        ("trunc(now, 15m)", "2026-05-23T12:15:00"),
        ("round(now, 15m)", "2026-05-23T12:15:00"),
        ("ceil(now, 15m)", "2026-05-23T12:30:00"),
        ("trunc(now, 1m)", "2026-05-23T12:15:00"),
        ("ceil(now, 1m)", "2026-05-23T12:16:00"),
        # Odd granularities count up from local midnight.
        ("trunc(now, 7h)", "2026-05-23T07:00:00"),
        ("ceil(now, 7h)", "2026-05-23T14:00:00"),
    ],
)
def test_rounding_an_instant_to_an_exact_granularity(env: Env, source: str, expected: str) -> None:
    assert wall(env, source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("trunc(now, 1d)", "2026-05-23"),
        ("ceil(now, 1d)", "2026-05-24"),
        ("round(now, 1d)", "2026-05-24"),
        # Week buckets are anchored on Monday; 2026-05-23 is a Saturday.
        ("trunc(now, 1w)", "2026-05-18"),
        ("ceil(now, 1w)", "2026-05-25"),
        # Month and year buckets, which used to be refused outright.
        ("trunc(now, 1mo)", "2026-05-01"),
        ("ceil(now, 1mo)", "2026-06-01"),
        ("trunc(now, 1y)", "2026-01-01"),
        ("ceil(now, 1y)", "2027-01-01"),
    ],
)
def test_a_calendar_granularity_yields_a_date(env: Env, source: str, expected: str) -> None:
    """The granularity decides the result type: a day-or-coarser bucket names
    a calendar day, so the answer is a date rather than a midnight instant."""
    assert date_of(env, source) == expected


def test_month_and_year_granularities_used_to_be_refused(env: Env) -> None:
    """They only ever errored because the result had to be an instant, and a
    month has no fixed length. A date needs none."""
    assert date_of(env, "trunc(now, 1mo)") == "2026-05-01"
    assert date_of(env, "trunc(today, 1y)") == "2026-01-01"


def test_rounding_down_to_a_day_is_unaffected_by_a_short_day(env: Env) -> None:
    """2026-03-08 in New York is 23 hours long. The answer is a date, which
    has no time of day for a clock change to shift."""
    assert date_of(env, "trunc(2026-03-08T23:30, 1d)") == "2026-03-08"


def test_rounding_down_to_a_day_is_unaffected_by_a_long_day(env: Env) -> None:
    """2026-11-01 in New York is 25 hours long."""
    assert date_of(env, "trunc(2026-11-01T23:30, 1d)") == "2026-11-01"


def test_an_exact_twenty_four_hour_bucket_is_not_a_calendar_day(env: Env) -> None:
    """`24h` is an exact bucket from midnight, so a 25-hour day overflows it.

    2026-11-01 in New York runs 25 hours, so midnight plus an exact 24 hours
    is 23:00 *the same evening* rather than the next midnight.  This is the
    four-ladder model being honest rather than a bug: ask for an exact
    granularity and you get exact arithmetic.
    """
    assert wall(env, "trunc(2026-11-01T23:30, 24h)") == "2026-11-01T23:00:00"
    assert date_of(env, "trunc(2026-11-01T23:30, 1d)") == "2026-11-01"


def test_a_date_already_on_a_boundary_is_unchanged(env: Env) -> None:
    assert date_of(env, "trunc(today, 1d)") == "2026-05-23"
    assert date_of(env, "ceil(today, 1d)") == "2026-05-23"


def test_a_business_day_granularity_is_an_error(env: Env) -> None:
    """It has no position within a month or a year to bucket by."""
    with pytest.raises(DtcalcError, match="no position within"):
        ev(env, "trunc(now, 1bd)")


def test_an_exact_granularity_on_a_date_is_an_error(env: Env) -> None:
    """The asymmetry: calendar granularities work on both types, exact ones
    only on instants, because a date has no time of day to round."""
    with pytest.raises(DtcalcError, match="no time of day to round"):
        ev(env, "trunc(today, 1h)")


def test_a_granularity_mixing_months_with_days_is_an_error(env: Env) -> None:
    with pytest.raises(DtcalcError, match="one ladder"):
        ev(env, "trunc(today, 1mo1d)")


def test_a_zero_granularity_is_an_error(env: Env) -> None:
    with pytest.raises(DtcalcError, match="zero"):
        ev(env, "trunc(now, 0s)")


def test_a_negative_granularity_is_an_error(env: Env) -> None:
    with pytest.raises(DtcalcError, match="positive"):
        ev(env, "trunc(now, -1h)")


# --------------------------------------------------------------------------
# 6.1  round / trunc / ceil on durations
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("round(97m, 15m)", "1h30m"),
        ("trunc(97m, 15m)", "1h30m"),
        ("ceil(97m, 15m)", "1h45m"),
        ("round(7m, 15m)", "0s"),
        ("ceil(1s, 1h)", "1h"),
        ("trunc(10d, 1w)", "7d"),
        ("ceil(10d, 1w)", "14d"),
        ("round(14mo, 1y)", "1y"),
        ("round(-97m, 15m)", "-1h30m"),
    ],
)
def test_rounding_a_duration(env: Env, source: str, expected: str) -> None:
    assert dur(env, source) == expected


def test_rounding_a_duration_across_ladders_is_an_error(env: Env) -> None:
    with pytest.raises(DtcalcError, match="same"):
        ev(env, "round(1d, 5h)")


def test_rounding_a_mixed_duration_is_an_error(env: Env) -> None:
    with pytest.raises(DtcalcError, match="same"):
        ev(env, "round(1d2h, 1h)")


# --------------------------------------------------------------------------
# 6.2  diff, epoch, epochms, unix
# --------------------------------------------------------------------------


def test_diff_gives_a_calendar_reading_where_subtraction_gives_elapsed_time(
    env: Env,
) -> None:
    ev(env, "a = 2026-11-01T00:30")
    ev(env, "b = 2026-11-02T00:30")
    assert dur(env, "diff(a, b)") == "1d"
    assert dur(env, "b - a") == "25h"


def test_diff_spans_months(env: Env) -> None:
    ev(env, "a = 2026-01-15T10:00")
    ev(env, "b = 2026-02-18T14:00")
    assert dur(env, "diff(a, b)") == "1mo3d4h"


def test_diff_is_signed(env: Env) -> None:
    ev(env, "a = now")
    ev(env, "b = now + 7d")
    assert dur(env, "diff(b, a)") == "-7d"


def test_epoch_builds_an_instant_from_unix_seconds(env: Env) -> None:
    assert wall(env, f"epoch({FROZEN_EPOCH:.0f})") == "2026-05-23T12:15:13"


def test_epochms_builds_an_instant_from_unix_milliseconds(env: Env) -> None:
    assert wall(env, f"epochms({FROZEN_EPOCH * 1000:.0f})") == "2026-05-23T12:15:13"


def test_there_is_no_magnitude_auto_detection(env: Env) -> None:
    """Seconds and milliseconds are different functions, on purpose."""
    assert wall(env, "epoch(1000)") != wall(env, "epochms(1000)")


def test_epoch_round_trips_with_unix(env: Env) -> None:
    assert ev(env, "unix(now)") == Number(FROZEN_EPOCH)
    assert wall(env, "epoch(unix(now))") == "2026-05-23T12:15:13"


def test_unix_is_unaffected_by_the_display_zone(env: Env) -> None:
    assert ev(env, "unix(now)") == ev(env, "unix(now in Tokyo)")


def test_epoch_out_of_range_is_a_clean_error(env: Env) -> None:
    with pytest.raises(DtcalcError, match="out of range"):
        ev(env, "epoch(999999999999999)")


# --------------------------------------------------------------------------
# 6.3  comparisons and booleans as a real value type
# --------------------------------------------------------------------------


def test_a_boolean_can_be_stored_and_compared(env: Env) -> None:
    ev(env, "p = 1h < 2h")
    ev(env, "q = 2h < 1h")
    assert ev(env, "p") == Boolean(True)
    assert ev(env, "p == q") == Boolean(False)
    assert ev(env, "p != q") == Boolean(True)


def test_instant_equality_is_exact_to_the_sub_second(env: Env) -> None:
    ev(env, "a = 2026-05-23T12:15:13")
    ev(env, "b = 2026-05-23T12:15:13.5")
    assert ev(env, "a == b") == Boolean(False)
    assert ev(env, "a < b") == Boolean(True)


def test_truncating_makes_a_fuzzy_comparison_possible(env: Env) -> None:
    ev(env, "a = 2026-05-23T12:15:13")
    ev(env, "b = 2026-05-23T12:15:13.5")
    assert ev(env, "trunc(a, 1s) == trunc(b, 1s)") == Boolean(True)


def test_rounding_a_half_goes_up(env: Env) -> None:
    ev(env, "b = 2026-05-23T12:15:13.5")
    assert wall(env, "round(b, 1s)") == "2026-05-23T12:15:14"


def test_functions_compose(env: Env) -> None:
    assert wall(env, "trunc(min(now, now + 1h), 1h)") == "2026-05-23T12:00:00"
