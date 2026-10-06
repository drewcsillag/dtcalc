"""The browser's view of dtcalc: one facade, no terminal.

The web front end runs this module under Pyodide and never touches
``repl`` (readline) or ``cli`` (argparse, colour).  It needs four things —
run a line, complete a line, save and restore the session, list the zones —
and they live here so the JavaScript stays a thin shell.

State is saved as versioned JSON rather than a pickle, so a blob written by
one release is readable, checkable and refusable by the next.  Variables keep
the language's eager semantics: a restored value is the stored value and is
never re-evaluated, so a restored ``now`` is the moment it was captured.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Final, assert_never
from zoneinfo import ZoneInfo

from dtcalc.clock import FixedClock, SystemClock
from dtcalc.date import Date
from dtcalc.duration import Duration
from dtcalc.env import Env
from dtcalc.errors import DtcalcError
from dtcalc.format import CLOCKS, FORMATS, PLAIN
from dtcalc.instant import Instant
from dtcalc.repl import completions
from dtcalc.resolve import Choice, Choices
from dtcalc.session import execute_line
from dtcalc.values import Boolean, Number, Value
from dtcalc.zones import all_zone_names, resolve_zone

__all__ = ["WebSession"]

_STATE_VERSION: Final = 1
_MS_PER_SECOND: Final = 1000
_MICROS_PER_MS: Final = 1000


def _clock_at(now_ms: int | None) -> FixedClock | SystemClock:
    if now_ms is None:
        return SystemClock()
    moment = datetime.fromtimestamp(now_ms // _MS_PER_SECOND, UTC)
    return FixedClock(moment.replace(microsecond=now_ms % _MS_PER_SECOND * _MICROS_PER_MS))


class WebSession:
    """A calculator session for the browser."""

    def __init__(self, zone: str, *, now_ms: int | None = None) -> None:
        self._env = Env(clock=_clock_at(now_ms), zone=resolve_zone(zone))

    def set_now(self, now_ms: int | None) -> None:
        """Freeze the clock at ``now_ms`` (epoch milliseconds), or release it."""
        self._env.clock = _clock_at(now_ms)

    def run(self, line: str) -> tuple[str, list[str]]:
        """Run one line; return the outcome name and plain-text output lines."""
        result = execute_line(line, self._env, PLAIN)
        lines = [part for block in result.lines for part in block.split("\n")]
        return result.outcome.name.lower(), lines

    def run_line(self, line: str, choices: str = "[]") -> str:
        """Like :meth:`run`, but able to ask which reading an ambiguous line means.

        ``choices`` is a JSON list of ``[start, end, "clock" | "duration"]``
        answers given so far; the reply is a JSON object with ``outcome``,
        ``lines`` and ``ambiguity``.  The last is ``null`` unless the line has
        a further unanswered ambiguity, in which case it holds the operator's
        ``key`` and the ``options`` to put to the user.  JSON both ways keeps
        the JavaScript free of Pyodide proxies.
        """
        result = execute_line(line, self._env, PLAIN, _parse_choices(choices))
        ambiguity = result.ambiguity
        return json.dumps(
            {
                "outcome": result.outcome.name.lower(),
                "lines": [part for block in result.lines for part in block.split("\n")],
                "ambiguity": None
                if ambiguity is None
                else {
                    "key": list(ambiguity.key),
                    "options": [asdict(option) for option in ambiguity.options],
                },
            }
        )

    def complete(self, line: str, cursor: int) -> list[str]:
        return completions(line, cursor, self._env)

    @staticmethod
    def zone_names() -> list[str]:
        return all_zone_names()

    # ------------------------------------------------------------------
    # saved state
    # ------------------------------------------------------------------

    def export_state(self) -> str:
        env = self._env
        return json.dumps(
            {
                "v": _STATE_VERSION,
                "zone": str(env.zone),
                "fmt": env.fmt,
                "clock": env.clock_style,
                "weeks": env.group_weeks,
                "vars": {name: _encode(value) for name, value in env.variables.items()},
            }
        )

    def import_state(self, blob: str) -> None:
        """Restore a saved session, all or nothing.

        Everything is decoded and checked before anything is applied, so a
        stale or damaged blob leaves the session exactly as it was.
        """
        try:
            data = json.loads(blob)
            if not isinstance(data, dict) or data.get("v") != _STATE_VERSION:
                raise ValueError("unrecognised format or version")
            zone = ZoneInfo(_text(data, "zone"))
            fmt = _choice(data, "fmt", FORMATS)
            clock = _choice(data, "clock", CLOCKS)
            weeks = data.get("weeks")
            if not isinstance(weeks, bool):
                raise ValueError("'weeks' must be true or false")
            raw = data.get("vars")
            if not isinstance(raw, dict):
                raise ValueError("'vars' must be an object")
            variables = {str(name): _decode(item) for name, item in raw.items()}
        except DtcalcError as error:
            raise DtcalcError(f"saved state is not usable: {error.message}") from error
        except (ValueError, TypeError, KeyError, OSError) as error:
            raise DtcalcError(f"saved state is not usable: {error}") from error

        env = self._env
        env.zone, env.fmt, env.clock_style, env.group_weeks = zone, fmt, clock, weeks
        env.variables = variables


_CHOICES: Final[tuple[Choice, ...]] = ("clock", "duration")


def _parse_choices(blob: str) -> Choices:
    try:
        raw = json.loads(blob)
        choices: dict[tuple[int, int], Choice] = {}
        for start, end, choice in raw:
            if choice not in _CHOICES or not isinstance(start, int) or not isinstance(end, int):
                raise ValueError(f"bad choice {choice!r}")
            choices[(start, end)] = choice
    except (ValueError, TypeError) as error:
        raise DtcalcError(f"choices are not usable: {error}") from error
    return choices


def _text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key!r} must be text")
    return value


def _number(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key!r} must be a whole number")
    return value


def _choice(data: dict[str, Any], key: str, allowed: tuple[str, ...]) -> str:
    value = _text(data, key)
    if value not in allowed:
        raise ValueError(f"{key!r} must be one of {', '.join(allowed)}")
    return value


def _encode(value: Value) -> dict[str, Any]:
    match value:
        case Date():
            return {"k": "date", "y": value.year, "m": value.month, "d": value.day}
        case Instant():
            return {
                "k": "instant",
                "utc": value.moment.astimezone(UTC).isoformat(),
                "zone": str(value.zone),
            }
        case Duration():
            return {
                "k": "duration",
                "mo": value.months,
                "d": value.days,
                "bd": value.bdays,
                "ms": value.millis,
            }
        case Number():
            return {"k": "number", "n": value.value}
        case Boolean():
            return {"k": "boolean", "b": value.value}
        case _ as unhandled:
            assert_never(unhandled)


def _decode_date(item: dict[str, Any]) -> Value:
    return Date(_number(item, "y"), _number(item, "m"), _number(item, "d"))


def _decode_instant(item: dict[str, Any]) -> Value:
    moment = datetime.fromisoformat(_text(item, "utc"))
    return Instant(moment.astimezone(UTC), ZoneInfo(_text(item, "zone")))


def _decode_duration(item: dict[str, Any]) -> Value:
    return Duration(
        months=_number(item, "mo"),
        days=_number(item, "d"),
        bdays=_number(item, "bd"),
        millis=_number(item, "ms"),
    )


def _decode_number(item: dict[str, Any]) -> Value:
    value = item.get("n")
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("'n' must be a number")
    return Number(float(value))


def _decode_boolean(item: dict[str, Any]) -> Value:
    value = item.get("b")
    if not isinstance(value, bool):
        raise ValueError("'b' must be true or false")
    return Boolean(value)


_DECODERS: Final[dict[str, Callable[[dict[str, Any]], Value]]] = {
    "date": _decode_date,
    "instant": _decode_instant,
    "duration": _decode_duration,
    "number": _decode_number,
    "boolean": _decode_boolean,
}


def _decode(item: object) -> Value:
    if not isinstance(item, dict):
        raise ValueError("a variable must be an object")
    kind = item.get("k")
    decoder = _DECODERS.get(kind) if isinstance(kind, str) else None
    if decoder is None:
        raise ValueError(f"unknown variable kind {kind!r}")
    return decoder(item)
