"""Tests for Instant: exact vs calendar arithmetic, DST policy, differences.

The trap this file exists to guard against: Python's ``datetime + timedelta``
on an aware datetime does *wall-clock* arithmetic, not elapsed-time
arithmetic.  Adding 24 hours to 2026-11-01T00:30 in New York that way gives
00:30 the next day, which is 25 real hours later.  Exact arithmetic has to
round-trip through UTC; calendar arithmetic works on wall-clock fields and
re-localizes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from dtcalc.duration import Duration
from dtcalc.errors import DtcalcError
from dtcalc.instant import Instant

from .support import NY, TOKYO, UTC_ZONE

D = Duration.build
LA = ZoneInfo("America/Los_Angeles")


def inst(zone: ZoneInfo, iso: str) -> Instant:
    return Instant.from_wall_clock(zone, datetime.fromisoformat(iso))


def wall(instant: Instant) -> str:
    return instant.wall_clock().isoformat()


# --------------------------------------------------------------------------
# construction, zones, rendering
# --------------------------------------------------------------------------


def test_wall_clock_round_trips() -> None:
    assert wall(inst(NY, "2026-05-23T12:15:13")) == "2026-05-23T12:15:13"


def test_the_display_zone_is_carried_on_the_value() -> None:
    assert inst(NY, "2026-05-23T12:15:13").zone == NY


def test_convert_changes_the_rendering_not_the_instant() -> None:
    original = inst(LA, "2026-05-23T12:13:00")
    converted = original.convert_to(NY)
    assert converted.moment == original.moment
    assert wall(converted) == "2026-05-23T15:13:00"
    assert converted.zone == NY


def test_the_original_request_sf_noon_is_afternoon_in_new_york() -> None:
    assert wall(inst(LA, "2026-05-23T12:13:00").convert_to(NY)) == "2026-05-23T15:13:00"


def test_canonical_rendering_is_iso_plus_the_zone_name() -> None:
    assert str(inst(NY, "2026-05-23T15:13:00")) == "2026-05-23T15:13:00-04:00  America/New_York"


def test_canonical_rendering_shows_fractional_seconds_only_when_present() -> None:
    assert str(inst(UTC_ZONE, "2026-05-23T15:13:00.5")) == "2026-05-23T15:13:00.5+00:00  UTC"


# --------------------------------------------------------------------------
# 2.2  exact vs calendar arithmetic
# --------------------------------------------------------------------------


def test_exact_addition_is_elapsed_time_across_a_fall_back() -> None:
    """+24h over the end of DST lands an hour earlier on the wall clock."""
    start = inst(NY, "2026-11-01T00:30:00")
    assert wall(start + D(h=24)) == "2026-11-01T23:30:00"


def test_calendar_day_addition_preserves_the_wall_clock_across_a_fall_back() -> None:
    start = inst(NY, "2026-11-01T00:30:00")
    assert wall(start + D(d=1)) == "2026-11-02T00:30:00"


def test_exact_and_calendar_agree_away_from_a_transition() -> None:
    start = inst(NY, "2026-05-23T12:15:13")
    assert wall(start + D(h=24)) == wall(start + D(d=1)) == "2026-05-24T12:15:13"


def test_the_original_request_seven_hours_from_noon() -> None:
    assert wall(inst(NY, "2026-05-23T12:15:13") + D(h=7)) == "2026-05-23T19:15:13"


def test_the_original_request_subtracting_a_colon_duration() -> None:
    """`2026-05-23T12:15:13 - 12:15` is `2026-05-23T00:00:13`."""
    assert wall(inst(NY, "2026-05-23T12:15:13") - D(h=12, m=15)) == "2026-05-23T00:00:13"


def test_the_original_request_adding_three_weeks_two_hours_five_minutes() -> None:
    assert wall(inst(NY, "2026-05-23T12:15:13") + D(w=3, h=2, m=5)) == "2026-06-13T14:20:13"


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        ("2026-01-31T09:00:00", 1, "2026-02-28T09:00:00"),
        ("2024-01-31T09:00:00", 1, "2024-02-29T09:00:00"),
        ("2026-03-31T09:00:00", 1, "2026-04-30T09:00:00"),
        ("2026-05-23T09:00:00", 12, "2027-05-23T09:00:00"),
        ("2026-03-31T09:00:00", -1, "2026-02-28T09:00:00"),
    ],
)
def test_calendar_month_addition_clamps_the_day_of_month(
    start: str, months: int, expected: str
) -> None:
    assert wall(inst(NY, start) + D(mo=months)) == expected


def test_weeks_are_seven_calendar_days() -> None:
    assert wall(inst(NY, "2026-05-23T09:00:00") + D(w=2)) == "2026-06-06T09:00:00"


@pytest.mark.parametrize(
    ("start", "bdays", "expected"),
    [
        # 2026-05-18 is a Monday.
        ("2026-05-18T09:00:00", 1, "2026-05-19T09:00:00"),
        ("2026-05-22T09:00:00", 1, "2026-05-25T09:00:00"),  # Friday -> Monday
        ("2026-05-23T09:00:00", 1, "2026-05-25T09:00:00"),  # Saturday -> Monday
        ("2026-05-24T09:00:00", 1, "2026-05-25T09:00:00"),  # Sunday -> Monday
        ("2026-05-18T09:00:00", 5, "2026-05-25T09:00:00"),
        ("2026-05-25T09:00:00", -1, "2026-05-22T09:00:00"),  # Monday -> Friday
        ("2026-05-23T09:00:00", -1, "2026-05-22T09:00:00"),  # Saturday -> Friday
        ("2026-05-18T09:00:00", 0, "2026-05-18T09:00:00"),
    ],
)
def test_business_day_arithmetic(start: str, bdays: int, expected: str) -> None:
    assert wall(inst(NY, start) + D(bd=bdays)) == expected


def test_business_days_do_not_skip_holidays() -> None:
    """Independence Day 2026 falls on a Saturday; 2026-07-03 is a Friday."""
    assert wall(inst(NY, "2026-07-02T09:00:00") + D(bd=1)) == "2026-07-03T09:00:00"


def test_mixed_duration_applies_calendar_parts_before_exact_parts() -> None:
    start = inst(NY, "2026-11-01T00:30:00")
    # 1 calendar day preserves the wall clock, then 2 exact hours are added.
    assert wall(start + D(d=1, h=2)) == "2026-11-02T02:30:00"


# --------------------------------------------------------------------------
# 2.3  DST edge-case policy
# --------------------------------------------------------------------------


def test_a_typed_nonexistent_wall_clock_time_is_an_error() -> None:
    with pytest.raises(DtcalcError, match="does not exist"):
        Instant.from_wall_clock(NY, datetime(2026, 3, 8, 2, 30), strict=True)


def test_a_typed_ambiguous_wall_clock_time_is_an_error() -> None:
    with pytest.raises(DtcalcError, match="happens twice"):
        Instant.from_wall_clock(NY, datetime(2026, 11, 1, 1, 30), strict=True)


def test_arithmetic_onto_a_nonexistent_time_shifts_forward_by_the_gap() -> None:
    result = inst(NY, "2026-03-07T02:30:00") + D(d=1)
    assert wall(result) == "2026-03-08T03:30:00"
    assert result.note is not None
    assert "does not exist" in result.note


def test_arithmetic_onto_an_ambiguous_time_picks_the_earlier_occurrence() -> None:
    result = inst(NY, "2026-10-31T01:30:00") + D(d=1)
    assert wall(result) == "2026-11-01T01:30:00"
    assert result.moment == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)  # EDT, the first pass
    assert result.note is not None
    assert "happens twice" in result.note


def test_a_note_does_not_affect_equality() -> None:
    plain = inst(NY, "2026-11-01T01:30:00")
    noted = inst(NY, "2026-10-31T01:30:00") + D(d=1)
    assert noted.moment == plain.moment


def test_unambiguous_arithmetic_carries_no_note() -> None:
    assert (inst(NY, "2026-05-23T09:00:00") + D(d=1)).note is None


# --------------------------------------------------------------------------
# 2.4  differences
# --------------------------------------------------------------------------


def test_instant_subtraction_is_an_exact_duration() -> None:
    a = inst(NY, "2026-05-23T12:15:13")
    b = inst(NY, "2026-05-23T17:15:13")
    assert b.elapsed_since(a) == D(h=5)
    assert str(b.elapsed_since(a)) == "5h"


def test_a_week_apart_reads_as_hours_because_the_result_is_exact() -> None:
    a = inst(NY, "2026-05-23T12:00:00")
    b = inst(NY, "2026-05-30T12:00:00")
    assert str(b.elapsed_since(a)) == "168h"


def test_subtraction_across_a_fall_back_counts_the_extra_hour() -> None:
    a = inst(NY, "2026-11-01T00:30:00")
    b = inst(NY, "2026-11-02T00:30:00")
    assert b.elapsed_since(a) == D(h=25)


def test_diff_decomposes_into_calendar_units() -> None:
    a = inst(NY, "2026-05-23T12:00:00")
    b = inst(NY, "2026-05-30T12:00:00")
    assert str(a.diff(b)) == "7d"


def test_diff_across_a_fall_back_still_reads_as_one_day() -> None:
    a = inst(NY, "2026-11-01T00:30:00")
    b = inst(NY, "2026-11-02T00:30:00")
    assert str(a.diff(b)) == "1d"
    assert str(b.elapsed_since(a)) == "25h"


def test_diff_mixes_months_days_and_hours() -> None:
    a = inst(NY, "2026-01-15T10:00:00")
    b = inst(NY, "2026-02-18T14:00:00")
    assert str(a.diff(b)) == "1mo3d4h"


def test_diff_is_signed() -> None:
    a = inst(NY, "2026-05-23T12:00:00")
    b = inst(NY, "2026-05-30T12:00:00")
    assert str(b.diff(a)) == "-7d"


def test_diff_of_an_instant_with_itself_is_zero() -> None:
    a = inst(NY, "2026-05-23T12:00:00")
    assert str(a.diff(a)) == "0s"


def test_diff_reconstructs_the_endpoint() -> None:
    a = inst(NY, "2026-01-15T10:00:00")
    b = inst(NY, "2026-02-18T14:00:00")
    assert (a + a.diff(b)).moment == b.moment


def test_subtraction_is_unaffected_by_the_display_zone() -> None:
    a = inst(NY, "2026-05-23T12:00:00")
    b = a.convert_to(TOKYO) + D(h=3)
    assert b.elapsed_since(a) == D(h=3)


# --------------------------------------------------------------------------
# 2.4a  range overflow
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "duration",
    [D(y=99999), D(y=-99999), D(d=4_000_000), D(h=100_000_000), D(bd=3_000_000)],
)
def test_walking_off_the_end_of_the_datetime_range_is_a_clean_error(
    duration: Duration,
) -> None:
    with pytest.raises(DtcalcError, match="out of range"):
        _ = inst(NY, "2026-05-23T12:00:00") + duration


def test_overflow_from_multiplication_is_also_clean() -> None:
    with pytest.raises(DtcalcError, match="out of range"):
        _ = inst(NY, "2026-05-23T12:00:00") + D(y=1000) * 1000.0
