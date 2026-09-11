"""Tests for the Date value type.

A date is a year, a month and a day. No time, and — the part that matters —
**no zone**, which is what makes `2027-01-03 - 2026-12-24` a span of ten days
rather than 240 hours.

The governing asymmetry: a date plus a *calendar* duration is still a date,
while a date plus anything carrying an exact part is not. `Duration` already
reports which of its four ladders it uses, so that is a predicate rather than
a special case.
"""

from __future__ import annotations

from datetime import date as StdDate
from datetime import datetime

import pytest

from dtcalc.date import Date
from dtcalc.duration import Duration
from dtcalc.errors import DtcalcError

from .support import NY, TOKYO, UTC_ZONE, d

D = Duration.build


# --------------------------------------------------------------------------
# 2.1  construction, ordering, rendering
# --------------------------------------------------------------------------


def test_construction_and_fields() -> None:
    value = Date(2026, 12, 24)
    assert (value.year, value.month, value.day) == (2026, 12, 24)


@pytest.mark.parametrize("iso", ["2026-12-24", "2026-01-01", "2024-02-29"])
def test_from_iso_round_trips(iso: str) -> None:
    assert str(Date.from_iso(iso)) == iso


@pytest.mark.parametrize("iso", ["2026-02-30", "2026-13-01", "2026-00-10", "not-a-date"])
def test_impossible_dates_are_rejected(iso: str) -> None:
    with pytest.raises(DtcalcError):
        Date.from_iso(iso)


def test_rendering_is_plain_iso() -> None:
    assert str(d("2026-12-24")) == "2026-12-24"
    assert repr(d("2026-12-24")) == "Date(2026-12-24)"


def test_single_digit_months_and_days_are_padded() -> None:
    assert str(Date(2026, 1, 5)) == "2026-01-05"


def test_equality_and_ordering() -> None:
    assert d("2026-12-24") == d("2026-12-24")
    assert d("2026-12-24") != d("2026-12-25")
    assert d("2026-12-24") < d("2026-12-25")
    assert d("2027-01-01") > d("2026-12-31")
    assert sorted([d("2027-01-03"), d("2026-12-24")]) == [d("2026-12-24"), d("2027-01-03")]


def test_hashable_so_it_can_be_a_dict_key() -> None:
    assert len({d("2026-12-24"), d("2026-12-24"), d("2026-12-25")}) == 2


def test_conversion_to_and_from_the_standard_library() -> None:
    assert d("2026-12-24").to_std() == StdDate(2026, 12, 24)
    assert Date.from_std(StdDate(2026, 12, 24)) == d("2026-12-24")


def test_weekday_matches_the_standard_library() -> None:
    # 2026-12-24 is a Thursday.
    assert d("2026-12-24").weekday() == 3


# --------------------------------------------------------------------------
# promotion to an instant, which every mixed rule goes through
# --------------------------------------------------------------------------


def test_at_midnight_in_a_zone() -> None:
    instant = d("2026-12-24").at_midnight(NY)
    assert instant.wall_clock().isoformat() == "2026-12-24T00:00:00"
    assert instant.zone == NY


def test_at_midnight_is_zone_specific() -> None:
    """The same date is a different moment in each zone."""
    assert d("2026-12-24").at_midnight(NY).moment != d("2026-12-24").at_midnight(TOKYO).moment


def test_at_midnight_in_utc() -> None:
    instant = d("2026-12-24").at_midnight(UTC_ZONE)
    assert instant.moment == datetime.fromisoformat("2026-12-24T00:00:00+00:00")


def test_at_a_named_time() -> None:
    instant = d("2026-12-24").at_time(NY, 16, 30, 0, 0)
    assert instant.wall_clock().isoformat() == "2026-12-24T16:30:00"


def test_at_midnight_survives_a_dst_transition_day() -> None:
    """2026-03-08 is the spring-forward day in New York; midnight still exists."""
    assert d("2026-03-08").at_midnight(NY).wall_clock().isoformat() == "2026-03-08T00:00:00"


# --------------------------------------------------------------------------
# 2.2  arithmetic
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "duration", "expected"),
    [
        ("2026-12-24", D(d=1), "2026-12-25"),
        ("2026-12-24", D(d=-1), "2026-12-23"),
        ("2026-12-24", D(w=1), "2026-12-31"),
        ("2026-12-24", D(w=2), "2027-01-07"),
        ("2026-12-24", D(d=10), "2027-01-03"),
        ("2026-12-24", D(mo=1), "2027-01-24"),
        ("2026-12-24", D(y=1), "2027-12-24"),
        ("2026-12-24", D(mo=-1), "2026-11-24"),
        # Day-of-month clamping, same rule as instants.
        ("2026-01-31", D(mo=1), "2026-02-28"),
        ("2024-01-31", D(mo=1), "2024-02-29"),
        ("2026-03-31", D(mo=-1), "2026-02-28"),
        # Business days: Mon-Fri, no holidays. 2026-12-24 is a Thursday.
        ("2026-12-24", D(bd=1), "2026-12-25"),
        ("2026-12-25", D(bd=1), "2026-12-28"),
        ("2026-12-26", D(bd=1), "2026-12-28"),
        ("2026-12-28", D(bd=-1), "2026-12-25"),
        ("2026-12-24", D(bd=0), "2026-12-24"),
        ("2026-12-24", D(), "2026-12-24"),
    ],
)
def test_adding_a_calendar_duration_keeps_it_a_date(
    start: str, duration: Duration, expected: str
) -> None:
    assert d(start) + duration == d(expected)


def test_subtracting_a_calendar_duration() -> None:
    assert d("2027-01-03") - D(d=10) == d("2026-12-24")


@pytest.mark.parametrize(
    ("later", "earlier", "expected"),
    [
        ("2027-01-03", "2026-12-24", "10d"),
        ("2026-12-25", "2026-12-24", "1d"),
        ("2026-12-24", "2026-12-24", "0s"),
        ("2026-12-24", "2027-01-03", "-10d"),
        ("2027-12-24", "2026-12-24", "365d"),
    ],
)
def test_date_minus_date_is_a_span_of_calendar_days(
    later: str, earlier: str, expected: str
) -> None:
    """The feature: the original request's example, in the requested unit."""
    difference = d(later).days_since(d(earlier))
    assert isinstance(difference, Duration)
    assert str(difference) == expected


def test_the_difference_spans_a_dst_transition_without_noticing() -> None:
    """A date has no time, so clock changes simply do not apply to it."""
    assert str(d("2026-03-09").days_since(d("2026-03-07"))) == "2d"


def test_adding_then_subtracting_returns_the_date() -> None:
    start = d("2026-12-24")
    assert (start + D(d=10)) - D(d=10) == start


@pytest.mark.parametrize("duration", [D(y=99999), D(y=-99999), D(d=4_000_000)])
def test_walking_off_the_end_of_the_range_is_a_clean_error(duration: Duration) -> None:
    with pytest.raises(DtcalcError, match="out of range"):
        _ = d("2026-12-24") + duration


# --------------------------------------------------------------------------
# 2.3  the promotion predicate
# --------------------------------------------------------------------------


@pytest.mark.parametrize("duration", [D(d=1), D(w=1), D(mo=1), D(y=1), D(bd=3), D()])
def test_calendar_durations_do_not_promote(duration: Duration) -> None:
    assert not Date.promotes(duration)


@pytest.mark.parametrize("duration", [D(h=3), D(m=90), D(s=1), D(ms=1), D(d=1, h=3)])
def test_anything_with_an_exact_part_promotes(duration: Duration) -> None:
    assert Date.promotes(duration)


def test_a_zero_exact_part_does_not_promote() -> None:
    """`+ 0s` touches the exact ladder but names no instant, so it stays a date."""
    assert not Date.promotes(D(s=0))
    assert not Date.promotes(D(ms=0))
    assert d("2026-12-24") + D(s=0) == d("2026-12-24")


def test_the_predicate_agrees_with_the_ladder_it_is_derived_from() -> None:
    """Guards the rule against a future change to how ladders are reported."""
    for duration in [D(d=1), D(mo=1), D(bd=1), D(h=1), D(d=1, h=1), D()]:
        assert Date.promotes(duration) == bool(duration.millis)


# --------------------------------------------------------------------------
# 2.4  diff
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ("2026-01-15", "2026-02-18", "1mo3d"),
        ("2026-01-15", "2026-01-15", "0s"),
        ("2026-01-15", "2026-01-20", "5d"),
        ("2026-01-31", "2026-03-31", "2mo"),
        ("2026-12-24", "2027-12-24", "1y"),
        ("2026-02-18", "2026-01-15", "-1mo3d"),
    ],
)
def test_diff_decomposes_into_months_and_days(start: str, end: str, expected: str) -> None:
    assert str(d(start).diff(d(end))) == expected


def test_diff_reconstructs_the_endpoint() -> None:
    start, end = d("2026-01-15"), d("2026-02-18")
    assert start + start.diff(end) == end


def test_diff_and_subtraction_answer_different_questions() -> None:
    """One says how many days, the other says how many months and days."""
    start, end = d("2026-01-15"), d("2026-02-18")
    assert str(end.days_since(start)) == "34d"
    assert str(start.diff(end)) == "1mo3d"
