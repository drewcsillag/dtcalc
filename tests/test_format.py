"""Tests for value formatting, the :fmt modes, and colour gating."""

from __future__ import annotations

import io
from datetime import date

import pytest

from dtcalc.duration import Duration
from dtcalc.errors import DtcalcError
from dtcalc.format import ANSI, FORMATS, PLAIN, Display, choose_style, format_value, render
from dtcalc.instant import Instant
from dtcalc.values import Boolean, Number

from .support import NY, TOKYO

D = Duration.build


def inst(iso: str, zone: object = NY) -> Instant:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    assert isinstance(zone, ZoneInfo)
    return Instant.from_wall_clock(zone, datetime.fromisoformat(iso))


# --------------------------------------------------------------------------
# 7.1  instant formats
# --------------------------------------------------------------------------


def test_the_default_format_is_iso_plus_the_zone_name() -> None:
    assert (
        format_value(inst("2026-05-23T15:13:00")) == "2026-05-23T15:13:00-04:00  America/New_York"
    )


def test_the_zone_name_makes_a_conversion_self_evident() -> None:
    converted = inst("2026-05-23T15:13:00").convert_to(TOKYO)
    assert format_value(converted) == "2026-05-24T04:13:00+09:00  Asia/Tokyo"


def test_the_human_format() -> None:
    assert (
        format_value(inst("2026-05-23T15:13:00"), Display(fmt="human"))
        == "Sat 2026-05-23 15:13:00 EDT"
    )


def test_the_human_format_names_the_standard_time_abbreviation_in_winter() -> None:
    assert format_value(inst("2026-01-23T15:13:00"), Display(fmt="human")).endswith("EST")


def test_the_unix_format() -> None:
    assert format_value(inst("2026-05-23T12:15:13"), Display(fmt="unix")) == "1779552913"


def test_fractional_seconds_appear_only_when_present() -> None:
    assert format_value(inst("2026-05-23T15:13:00.5")).startswith("2026-05-23T15:13:00.5")
    assert format_value(inst("2026-05-23T15:13:00.5"), Display(fmt="human")).endswith(".5 EDT")


def test_the_full_date_is_always_printed() -> None:
    """Even for a time today, so arithmetic that rolled over is visible."""
    for fmt in FORMATS:
        rendered = format_value(inst("2026-05-23T15:13:00"), Display(fmt=fmt))
        assert rendered.strip() != "15:13:00"


def test_an_unknown_format_is_an_error() -> None:
    with pytest.raises(DtcalcError, match="unknown format"):
        format_value(inst("2026-05-23T15:13:00"), Display(fmt="nope"))


# --------------------------------------------------------------------------
# 7.1  other value types across the modes
# --------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["iso", "human", "timeonly"])
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (D(w=3, h=2, m=5), "3w2h5m"),
        (D(h=24), "24h"),
        (D(), "0s"),
        (Number(8.0), "8"),
        (Number(0.5), "0.5"),
        (Boolean(True), "true"),
        (Boolean(False), "false"),
    ],
)
def test_non_instants_look_the_same_except_in_unix(value: object, expected: str, fmt: str) -> None:
    assert format_value(value, Display(fmt=fmt)) == expected  # type: ignore[arg-type]


def test_unix_mode_prints_a_duration_as_bare_seconds() -> None:
    """The one place a format mode reaches past instants: everything
    coming out of unix mode should be a number a pipeline can read."""
    assert format_value(D(h=1, m=30), Display(fmt="unix")) == "5400"
    assert format_value(D(ms=1500), Display(fmt="unix")) == "1.5"


def test_unix_mode_refuses_a_calendar_duration() -> None:
    with pytest.raises(DtcalcError, match="no fixed number of seconds"):
        format_value(D(d=1), Display(fmt="unix"))


def test_unix_mode_leaves_numbers_and_booleans_alone() -> None:
    assert format_value(Number(8.0), Display(fmt="unix")) == "8"
    assert format_value(Boolean(True), Display(fmt="unix")) == "true"


# --------------------------------------------------------------------------
# notes
# --------------------------------------------------------------------------


def test_render_appends_an_advisory_note() -> None:
    shifted = inst("2026-03-07T02:30:00") + D(d=1)
    lines = render(shifted)
    assert len(lines) == 2
    assert lines[0].startswith("2026-03-08T03:30:00")
    assert "does not exist" in lines[1]


def test_render_is_a_single_line_without_a_note() -> None:
    assert len(render(inst("2026-05-23T15:13:00"))) == 1


# --------------------------------------------------------------------------
# 7.2  colour gating
# --------------------------------------------------------------------------


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


class _Pipe(io.StringIO):
    def isatty(self) -> bool:
        return False


def test_colour_is_on_for_a_terminal() -> None:
    assert choose_style(stream=_Tty(), env={}) is ANSI


def test_colour_is_off_for_a_pipe() -> None:
    assert choose_style(stream=_Pipe(), env={}) is PLAIN


def test_no_color_environment_variable_wins() -> None:
    assert choose_style(stream=_Tty(), env={"NO_COLOR": "1"}) is PLAIN


def test_the_no_color_flag_wins() -> None:
    assert choose_style(stream=_Tty(), env={}, no_color=True) is PLAIN


def test_a_stream_that_cannot_be_asked_is_treated_as_a_pipe() -> None:
    assert choose_style(stream=None, env={}) in {ANSI, PLAIN}


def test_the_ansi_style_wraps_the_three_coloured_things() -> None:
    assert ANSI.prompt("dtcalc> ") == "\x1b[36mdtcalc> \x1b[0m"
    assert ANSI.result("2h") == "\x1b[32m2h\x1b[0m"
    assert ANSI.error("error: nope") == "\x1b[31merror: nope\x1b[0m"


def test_the_plain_style_adds_nothing() -> None:
    assert PLAIN.prompt("dtcalc> ") == "dtcalc> "
    assert PLAIN.result("2h") == "2h"
    assert PLAIN.error("error: nope") == "error: nope"
    assert "\x1b" not in PLAIN.result("2h")


# --------------------------------------------------------------------------
# 11.4  timeonly and the 12h/24h modifier
# --------------------------------------------------------------------------

TODAY = date(2026, 5, 23)


def show(iso: str, **kwargs: object) -> str:
    display = Display(today=TODAY, **kwargs)  # type: ignore[arg-type]
    return format_value(inst(iso), display)


def test_timeonly_drops_the_date() -> None:
    assert show("2026-05-23T16:00:00", fmt="timeonly") == "16:00:00 EDT"


def test_timeonly_marks_a_different_day_so_a_rollover_cannot_hide() -> None:
    assert show("2026-05-24T07:00:00", fmt="timeonly") == "07:00:00 EDT (+1d)"
    assert show("2026-05-22T07:00:00", fmt="timeonly") == "07:00:00 EDT (-1d)"
    assert show("2026-05-30T07:00:00", fmt="timeonly") == "07:00:00 EDT (+7d)"


def test_timeonly_shows_fractional_seconds_when_present() -> None:
    assert show("2026-05-23T16:00:00.5", fmt="timeonly") == "16:00:00.5 EDT"


@pytest.mark.parametrize(
    ("iso", "expected"),
    [
        ("2026-05-23T16:00:00", "4:00:00 PM EDT"),
        ("2026-05-23T04:00:00", "4:00:00 AM EDT"),
        ("2026-05-23T00:00:00", "12:00:00 AM EDT"),
        ("2026-05-23T12:00:00", "12:00:00 PM EDT"),
        ("2026-05-23T23:59:59", "11:59:59 PM EDT"),
    ],
)
def test_timeonly_on_a_twelve_hour_clock(iso: str, expected: str) -> None:
    assert show(iso, fmt="timeonly", clock="12h") == expected


def test_the_twelve_hour_clock_round_trips_through_the_language() -> None:
    """What `timeonly 12h` prints is what a meridiem literal accepts."""
    assert show("2026-05-23T16:30:00", fmt="timeonly", clock="12h").startswith("4:30:00 PM")


def test_human_honours_the_clock_modifier() -> None:
    assert show("2026-05-23T15:13:00", fmt="human") == "Sat 2026-05-23 15:13:00 EDT"
    assert show("2026-05-23T15:13:00", fmt="human", clock="12h") == "Sat 2026-05-23 3:13:00 PM EDT"


def test_iso_ignores_the_clock_modifier() -> None:
    """A 12-hour ISO 8601 timestamp is not ISO 8601, and would break parsers."""
    assert show("2026-05-23T15:13:00", fmt="iso", clock="12h") == show(
        "2026-05-23T15:13:00", fmt="iso", clock="24h"
    )


def test_unix_ignores_the_clock_modifier() -> None:
    assert show("2026-05-23T15:13:00", fmt="unix", clock="12h") == "1779563580"


@pytest.mark.parametrize("clock", ["12h", "24h"])
def test_non_instants_ignore_both_settings(clock: str) -> None:
    display = Display(fmt="timeonly", clock=clock, today=TODAY)
    assert format_value(D(h=1, m=30), display) == "1h30m"
    assert format_value(Number(8.0), display) == "8"
    assert format_value(Boolean(True), display) == "true"


def test_an_unknown_clock_setting_is_an_error() -> None:
    with pytest.raises(DtcalcError, match="unknown clock"):
        format_value(inst("2026-05-23T16:00:00"), Display(clock="13h", today=TODAY))


def test_timeonly_without_a_reference_date_omits_the_marker() -> None:
    """A formatter with no notion of today still prints something sensible."""
    assert format_value(inst("2026-05-24T07:00:00"), Display(fmt="timeonly")) == "07:00:00 EDT"
