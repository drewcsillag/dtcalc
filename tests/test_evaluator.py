"""Tests for the evaluator, with a frozen clock so `now` is deterministic.

The frozen clock reads 2026-05-23T12:15:13 in New York, which is the
timestamp from the original feature request — so the worked examples in that
request are literally the examples here.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

import pytest

from dtcalc.date import Date
from dtcalc.duration import Duration
from dtcalc.env import Env
from dtcalc.errors import DtcalcError
from dtcalc.evaluator import evaluate_line
from dtcalc.instant import Instant
from dtcalc.values import Boolean, Number

from .support import NY, TEST_NOW

D = Duration.build
LA = ZoneInfo("America/Los_Angeles")


@pytest.fixture
def env() -> Env:
    from dtcalc.clock import FixedClock

    return Env(clock=FixedClock(TEST_NOW), zone=NY)


def ev(env: Env, source: str) -> object:
    return evaluate_line(source, env)


def wall(env: Env, source: str) -> str:
    value = ev(env, source)
    assert isinstance(value, Instant), f"{source} gave {value!r}"
    return value.wall_clock().isoformat()


def date_of(env: Env, source: str) -> str:
    """For expressions that now evaluate to a date rather than a midnight instant."""
    value = ev(env, source)
    assert isinstance(value, Date), f"{source} gave {value!r}"
    return str(value)


def dur(env: Env, source: str) -> str:
    value = ev(env, source)
    assert isinstance(value, Duration)
    return str(value)


# --------------------------------------------------------------------------
# the original request, end to end
# --------------------------------------------------------------------------


def test_now_plus_seven_hours(env: Env) -> None:
    assert wall(env, "now + 7h") == "2026-05-23T19:15:13"


def test_subtracting_a_colon_duration(env: Env) -> None:
    assert wall(env, "2026-05-23T12:15:13 - 12:15") == "2026-05-23T00:00:13"


def test_adding_three_weeks_two_hours_five_minutes(env: Env) -> None:
    assert wall(env, "2026-05-23T12:15:13 + 3w2h5m") == "2026-06-13T14:20:13"


def test_san_francisco_noon_seen_from_new_york(env: Env) -> None:
    assert wall(env, "12:13 @ SanFrancisco") == "2026-05-23T15:13:00"


def test_variables(env: Env) -> None:
    ev(env, "foo = now")
    assert wall(env, "bar = foo + 5h") == "2026-05-23T17:15:13"
    assert wall(env, "bar") == "2026-05-23T17:15:13"
    assert wall(env, "foo - 5h") == "2026-05-23T07:15:13"


def test_scalar_multiplication(env: Env) -> None:
    assert dur(env, "3h * 5") == "15h"


def test_eight_hours_times_three_is_twenty_four_hours_not_one_day(env: Env) -> None:
    """Days are calendar units, so hours never promote into them."""
    assert dur(env, "8h * 3") == "24h"


# --------------------------------------------------------------------------
# 5.1  the operator table
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("now + 1h", "2026-05-23T13:15:13"),
        ("now - 1h", "2026-05-23T11:15:13"),
        ("now + 1d", "2026-05-24T12:15:13"),
        ("now + 1mo", "2026-06-23T12:15:13"),
        ("now + 1y", "2027-05-23T12:15:13"),
        ("now + 1bd", "2026-05-25T12:15:13"),
        ("today 09:30", "2026-05-23T09:30:00"),
        ("tomorrow 09:00", "2026-05-24T09:00:00"),
        ("2026-05-23T12:15", "2026-05-23T12:15:00"),
        ("2026-05-23 12:15:13", "2026-05-23T12:15:13"),
        ("2026-05-23T12:15:13Z", "2026-05-23T08:15:13"),
        ("2026-05-23T12:15:13-07:00", "2026-05-23T15:15:13"),
        ("12:15", "2026-05-23T12:15:00"),
        ("(now + 1d) in Tokyo", "2026-05-25T01:15:13"),
        ("now in utc", "2026-05-23T16:15:13"),
    ],
)
def test_instant_expressions(env: Env, source: str, expected: str) -> None:
    assert wall(env, source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("3h + 45m", "3h45m"),
        ("1d - 90m", "1d -1h30m"),
        ("2h * 3", "6h"),
        ("3 * 2h", "6h"),
        ("24h / 4", "6h"),
        ("97m % 15m", "7m"),
        ("-5h", "-5h"),
        ("1h - 30m", "30m"),
        ("1:02:03h", "1h2m3s"),
        (":12:15", "12m15s"),
        ("::15", "15s"),
        ("12:15m", "12m15s"),
        ("250ms * 4", "1s"),
    ],
)
def test_duration_expressions(env: Env, source: str, expected: str) -> None:
    assert dur(env, source) == expected


def test_instant_minus_instant_is_an_exact_duration(env: Env) -> None:
    ev(env, "a = now")
    ev(env, "b = now + 5h")
    assert dur(env, "b - a") == "5h"


def test_a_week_apart_reads_in_hours(env: Env) -> None:
    ev(env, "a = now")
    ev(env, "b = now + 7d")
    assert dur(env, "b - a") == "168h"


@pytest.mark.parametrize(
    ("source", "expected"),
    [("2h / 15m", 8.0), ("1d / 1d", 1.0), ("15h / 3h", 5.0)],
)
def test_duration_divided_by_duration(env: Env, source: str, expected: float) -> None:
    assert ev(env, source) == Number(expected)


def test_zone_conversion_keeps_the_instant(env: Env) -> None:
    ev(env, "a = now")
    ev(env, "b = now in Tokyo")
    assert ev(env, "a == b") == Boolean(True)


def test_attach_reinterprets_the_wall_clock(env: Env) -> None:
    assert wall(env, "12:13 @ America/Los_Angeles") == "2026-05-23T15:13:00"


def test_attach_then_convert(env: Env) -> None:
    assert wall(env, "12:13 @ sf in Tokyo") == "2026-05-24T04:13:00"


def test_the_display_zone_is_carried_through_arithmetic(env: Env) -> None:
    value = ev(env, "(now in Tokyo) + 1h")
    assert isinstance(value, Instant)
    assert value.zone == ZoneInfo("Asia/Tokyo")


# --------------------------------------------------------------------------
# weekday and day-of-month references
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # 2026-05-23 is a Saturday.
        ("upcoming monday", "2026-05-25"),
        ("upcoming friday", "2026-05-29"),
        ("upcoming saturday", "2026-05-30"),
        ("previous friday", "2026-05-22"),
        ("previous saturday", "2026-05-16"),
    ],
)
def test_weekday_references_are_strictly_after_or_before_today(
    env: Env, source: str, expected: str
) -> None:
    """These are dates now: no time was named, so none is invented."""
    assert date_of(env, source) == expected


def test_a_weekday_reference_with_a_time_is_an_instant(env: Env) -> None:
    assert wall(env, "upcoming friday 09:00") == "2026-05-29T09:00:00"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("upcoming 1st", "2026-06-01"),
        ("upcoming 15th", "2026-06-15"),
        ("upcoming 24th", "2026-05-24"),
        ("previous 1st", "2026-05-01"),
        ("previous 23rd", "2026-04-23"),
        ("upcoming 31st", "2026-05-31"),
    ],
)
def test_day_of_month_references(env: Env, source: str, expected: str) -> None:
    assert date_of(env, source) == expected


def test_a_day_of_month_reference_skips_months_that_lack_the_day(env: Env) -> None:
    ev(env, "x = 2026-01-31")
    # From 31 January, the next 31st is in March: February has no 31st.
    assert date_of(env, "upcoming 31st") == "2026-05-31"


def test_upcoming_on_the_same_day_of_month_goes_to_next_month(env: Env) -> None:
    assert date_of(env, "upcoming 23rd") == "2026-06-23"


# --------------------------------------------------------------------------
# comparisons
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("now < now + 1h", True),
        ("now > now + 1h", False),
        ("now <= now", True),
        ("now >= now", True),
        ("now == now", True),
        ("now != now", False),
        ("1h < 2h", True),
        ("1d < 25h", True),
        ("1d == 24h", True),
        ("1h == 60m", True),
        ("2h / 15m == 8", True),
    ],
)
def test_comparisons(env: Env, source: str, expected: bool) -> None:
    assert ev(env, source) == Boolean(expected)


def test_comparing_a_month_against_hours_is_an_error(env: Env) -> None:
    with pytest.raises(DtcalcError, match="compare"):
        ev(env, "1mo < 720h")


def test_booleans_are_storable(env: Env) -> None:
    ev(env, "later = now < now + 1h")
    assert ev(env, "later") == Boolean(True)


# --------------------------------------------------------------------------
# 5.2  variables
# --------------------------------------------------------------------------


def test_assignment_is_eager(env: Env) -> None:
    """`foo = now` captures a value; it is not a live reading of the clock."""
    first = ev(env, "foo = now")
    second = ev(env, "foo")
    assert first == second


def test_assignment_returns_the_stored_value(env: Env) -> None:
    assert ev(env, "x = 3h") == D(h=3)


def test_reassignment_replaces(env: Env) -> None:
    ev(env, "x = 3h")
    ev(env, "x = 5h")
    assert ev(env, "x") == D(h=5)


def test_a_variable_can_be_defined_from_itself(env: Env) -> None:
    ev(env, "x = 1h")
    ev(env, "x = x + 1h")
    assert ev(env, "x") == D(h=2)


@pytest.mark.parametrize(
    "name", ["now", "today", "tomorrow", "yesterday", "in", "upcoming", "previous"]
)
def test_keywords_cannot_be_variable_names(env: Env, name: str) -> None:
    with pytest.raises(DtcalcError):
        ev(env, f"{name} = 3h")


@pytest.mark.parametrize("name", ["s", "m", "h", "d", "w", "y", "mo", "ms", "bd"])
def test_unit_names_cannot_be_variable_names(env: Env, name: str) -> None:
    with pytest.raises(DtcalcError, match="unit"):
        ev(env, f"{name} = 3h")


@pytest.mark.parametrize("name", ["min", "max", "round", "trunc", "diff", "epoch", "unix"])
def test_function_names_cannot_be_variable_names(env: Env, name: str) -> None:
    with pytest.raises(DtcalcError, match="function"):
        ev(env, f"{name} = 3h")


@pytest.mark.parametrize("name", ["monday", "fri", "sat"])
def test_weekday_names_cannot_be_variable_names(env: Env, name: str) -> None:
    with pytest.raises(DtcalcError):
        ev(env, f"{name} = 3h")


def test_an_undefined_variable_is_a_clear_error(env: Env) -> None:
    with pytest.raises(DtcalcError, match="undefined variable 'nope'"):
        ev(env, "nope + 1h")


# --------------------------------------------------------------------------
# type errors
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "fragment"),
    [
        ("now + now", "cannot add two points in time"),
        ("5h in Tokyo", "a date or an instant"),
        ("-now", "negate"),
        ("now * 2", "cannot multiply"),
        ("now / 2", "cannot divide"),
        ("2 + now", "duration"),
        ("1mo / 4", "evenly"),
        ("1d % 5h", "same"),
        ("1h / 0", "zero"),
        ("now in Atlantis", "unknown timezone"),
        ("now < 1h", "compare"),
        ("2 < 1h", "compare"),
    ],
)
def test_type_errors(env: Env, source: str, fragment: str) -> None:
    with pytest.raises(DtcalcError, match=fragment):
        ev(env, source)


def test_a_nonexistent_typed_literal_is_rejected(env: Env) -> None:
    with pytest.raises(DtcalcError, match="does not exist"):
        ev(env, "2026-03-08T02:30")


def test_an_ambiguous_typed_literal_is_rejected(env: Env) -> None:
    with pytest.raises(DtcalcError, match="happens twice"):
        ev(env, "2026-11-01T01:30")


def test_arithmetic_onto_a_dst_gap_carries_a_note(env: Env) -> None:
    value = ev(env, "2026-03-07T02:30 + 1d")
    assert isinstance(value, Instant)
    assert value.note is not None


def test_addition_is_commutative_across_kinds(env: Env) -> None:
    assert wall(env, "1h + now") == wall(env, "now + 1h")


def test_now_is_read_once_per_line(env: Env) -> None:
    assert ev(env, "now == now") == Boolean(True)
    assert ev(env, "now - now") == D()


# --------------------------------------------------------------------------
# 11.3  `expr @ <time>` — keep the date, replace the time
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("now @ 16:00", "2026-05-23T16:00:00"),
        ("now @ 4p", "2026-05-23T16:00:00"),
        ("now @ 4a", "2026-05-23T04:00:00"),
        ("now @ 12a", "2026-05-23T00:00:00"),
        ("now @ 12p", "2026-05-23T12:00:00"),
        ("now @ 4:30pm", "2026-05-23T16:30:00"),
        ("tomorrow @ 9:15", "2026-05-24T09:15:00"),
        ("(now + 1d) @ 17:00", "2026-05-24T17:00:00"),
        ("upcoming friday @ 4p", "2026-05-29T16:00:00"),
    ],
)
def test_at_a_time_replaces_the_time_and_keeps_the_date(
    env: Env, source: str, expected: str
) -> None:
    assert wall(env, source) == expected


def test_at_a_time_works_on_a_variable(env: Env) -> None:
    ev(env, "deploy = 2026-07-04T09:00")
    assert wall(env, "deploy @ 4p") == "2026-07-04T16:00:00"


def test_at_a_time_uses_the_date_as_displayed(env: Env) -> None:
    """The date comes from the wall clock in the display zone, not from UTC."""
    assert wall(env, "(now in Tokyo) @ 9:00") == "2026-05-24T09:00:00"


def test_at_a_time_then_subtract(env: Env) -> None:
    assert dur(env, "(now @ 16:00) - (now @ 12:00)") == "4h"


def test_a_bare_meridiem_literal_is_today_at_that_time(env: Env) -> None:
    assert wall(env, "4p") == "2026-05-23T16:00:00"
    assert wall(env, "7:30a") == "2026-05-23T07:30:00"


def test_at_a_zone_is_unaffected(env: Env) -> None:
    assert wall(env, "12:13 @ SanFrancisco") == "2026-05-23T15:13:00"
