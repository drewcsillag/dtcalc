"""Rendering values, and the colour layer.

The canonical rendering of each value lives on the value itself — see
:meth:`dtcalc.duration.Duration.__str__` and
:meth:`dtcalc.instant.Instant.__str__`.  This module adds the two things that
sit on top: the alternative instant formats that ``:fmt`` selects, and
colour.

``:fmt`` is fundamentally an *instant* mode.  Durations, numbers and booleans
look the same in ``iso``, ``human`` and ``timeonly``.  The one exception is
``unix``, where a duration prints as a bare count of seconds — the point of
that mode is that everything coming out of it is a number a pipeline can
consume.

Week grouping is a display choice too: ``10d`` by default, ``1w3d`` when
asked for.  It reaches the day ladder only -- ``15mo`` is ``1y3mo`` either
way, because years group more naturally than weeks.

``timeonly`` drops the date, for arithmetic where the date is not the point.
It appends a relative day marker when the result is not on today's date, so
that ``now + 20h`` cannot silently look like a time this morning.  That
marker is what makes dropping the date safe.

The 12-hour clock applies to ``human`` and ``timeonly``.  It deliberately
does *not* apply to ``iso``: a 12-hour ISO 8601 timestamp is not ISO 8601 and
would break anything parsing the output.  ``unix`` has no clock at all.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import IO, Final

from dtcalc.duration import Duration
from dtcalc.errors import DtcalcError
from dtcalc.instant import Instant
from dtcalc.values import Value, format_number

__all__ = [
    "CLOCKS",
    "FORMATS",
    "GROUPINGS",
    "Display",
    "Style",
    "choose_style",
    "format_value",
    "render",
]

FORMATS: Final = ("iso", "human", "unix", "timeonly")
CLOCKS: Final = ("24h", "12h")
GROUPINGS: Final = ("noweeks", "weeks")

_MS_PER_SECOND: Final = 1000


@dataclass(frozen=True, slots=True)
class Display:
    """How to render a value.

    ``today`` is the reference date for ``timeonly``'s day marker.  It is
    supplied rather than read from the clock so the formatter stays a pure
    function of its inputs.
    """

    fmt: str = "iso"
    clock: str = "24h"
    group_weeks: bool = False
    today: date | None = None


@dataclass(frozen=True, slots=True)
class Style:
    """ANSI wrappers for the three things that get coloured.

    Prompt, results and errors — no more than that, so output stays legible
    rather than decorated.
    """

    prompt_code: str = ""
    result_code: str = ""
    error_code: str = ""

    def prompt(self, text: str) -> str:
        return self._wrap(text, self.prompt_code)

    def result(self, text: str) -> str:
        return self._wrap(text, self.result_code)

    def error(self, text: str) -> str:
        return self._wrap(text, self.error_code)

    @staticmethod
    def _wrap(text: str, code: str) -> str:
        return f"{code}{text}\x1b[0m" if code else text


ANSI: Final = Style(prompt_code="\x1b[36m", result_code="\x1b[32m", error_code="\x1b[31m")
PLAIN: Final = Style()


def choose_style(
    *,
    stream: IO[str] | None = None,
    no_color: bool = False,
    env: Mapping[str, str] | None = None,
) -> Style:
    """Colour when the output is a terminal and nobody has asked us not to.

    Honours ``--no-color`` and the ``NO_COLOR`` convention, and stays plain
    whenever the destination is a pipe or a file — which is also what keeps
    the golden transcripts free of escape codes.
    """
    if no_color:
        return PLAIN
    environment = os.environ if env is None else env
    if environment.get("NO_COLOR"):
        return PLAIN
    target = sys.stdout if stream is None else stream
    try:
        interactive = target.isatty()
    except (AttributeError, ValueError):
        interactive = False
    return ANSI if interactive else PLAIN


def format_value(value: Value, display: Display | None = None) -> str:
    """Render a value for display."""
    settings = Display() if display is None else display
    if settings.fmt not in FORMATS:
        raise DtcalcError(
            f"unknown format {settings.fmt!r}; the ones there are: {', '.join(FORMATS)}"
        )
    if settings.clock not in CLOCKS:
        raise DtcalcError(
            f"unknown clock {settings.clock!r}; the ones there are: {', '.join(CLOCKS)}"
        )

    if isinstance(value, Instant):
        return _format_instant(value, settings)
    if isinstance(value, Duration):
        if settings.fmt == "unix":
            return format_number(_total_seconds(value))
        return value.render(group_weeks=settings.group_weeks)
    return str(value)


def render(value: Value, display: Display | None = None) -> list[str]:
    """The lines to print for a result: the value, plus any advisory note."""
    lines = [format_value(value, display)]
    if isinstance(value, Instant) and value.note is not None:
        lines.append(value.note)
    return lines


def _format_instant(value: Instant, display: Display) -> str:
    aware = value.aware()
    match display.fmt:
        case "human":
            clock = _format_clock(aware, display.clock)
            return f"{aware.strftime('%a %Y-%m-%d')} {clock} {aware.tzname()}"
        case "timeonly":
            clock = _format_clock(aware, display.clock)
            return f"{clock} {aware.tzname()}{_day_marker(aware.date(), display.today)}"
        case "unix":
            return format_number(value.moment.timestamp())
        case _:
            return str(value)


def _format_clock(aware: datetime, clock: str) -> str:
    """The time of day, on a 24- or 12-hour clock, with fractions if present."""
    if clock == "12h":
        hour = aware.hour % 12 or 12
        stamp = f"{hour}:{aware.minute:02d}:{aware.second:02d}"
        suffix = f" {'AM' if aware.hour < 12 else 'PM'}"
    else:
        stamp = f"{aware.hour:02d}:{aware.minute:02d}:{aware.second:02d}"
        suffix = ""
    if aware.microsecond:
        stamp += f".{aware.microsecond:06d}".rstrip("0")
    return stamp + suffix


def _day_marker(day: date, today: date | None) -> str:
    """``(+1d)`` when the result is not on today's date.

    Without this, dropping the date would let ``now + 20h`` read as a time
    this morning.  It appears only when it matters.
    """
    if today is None or day == today:
        return ""
    offset = (day - today).days
    return f" ({offset:+d}d)"


def _total_seconds(value: Duration) -> float:
    """A duration as seconds, for ``unix`` mode only.

    Calendar parts are refused rather than approximated: a month has no
    number of seconds, and guessing one would corrupt whatever consumes the
    output.
    """
    if value.months or value.days or value.bdays:
        raise DtcalcError(
            f"{value} has calendar parts, so it has no fixed number of seconds; "
            f"unix format cannot print it"
        )
    return value.millis / _MS_PER_SECOND
