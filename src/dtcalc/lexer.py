"""The lexer.

Hand-written rather than generated, because the interesting parts are the
ambiguities and those are easier to read as explicit ordered attempts than as
a grammar with precedence hacks:

* A date literal is exactly ``YYYY-MM-DD``, matched greedily, so the hyphens
  inside it never compete with subtraction.  ``2026-05-23-5h`` is a date minus
  five hours.
* A trailing UTC offset must be ``Z`` or ``±HH:MM`` with the colon, so
  ``...13-5h`` is a subtraction rather than a malformed offset.
* Unit suffixes are matched longest-first, so ``3m``, ``3ms`` and ``3mo`` are
  three different durations, and ``3bd`` is business days rather than days.
* A leading ``:`` introduces a colon literal when a digit or another colon
  follows it, and a meta-command when a letter does.
* ``#`` starts a comment, which runs to the end of the line.
* A meridiem suffix (``4p``, ``4:30pm``) makes a 12-hour clock reading, and is
  tried before the colon-literal, ordinal, duration and number scanners —
  ``4p`` would otherwise be a malformed number and ``4:30p`` would trip the
  colon literal's suffix check.

Colon literals are *not* resolved here.  The lexer records what was written —
the fields, which unit the leftmost one names, and whether the form rules out
a time-of-day reading — and :mod:`dtcalc.resolve` decides what it means.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

from dtcalc.duration import Duration
from dtcalc.errors import DtcalcError

__all__ = [
    "ClockLiteral",
    "ColonLiteral",
    "DateTimeLiteral",
    "Token",
    "TokenKind",
    "is_meta_command",
    "tokenize",
]


class TokenKind(StrEnum):
    NUMBER = "number"
    CLOCK = "clock time"
    DURATION = "duration"
    COLON_LITERAL = "colon literal"
    DATETIME = "datetime"
    DATE = "date"
    IDENT = "identifier"
    ORDINAL = "ordinal"
    WEEKDAY = "weekday"
    NOW = "now"
    TODAY = "today"
    TOMORROW = "tomorrow"
    YESTERDAY = "yesterday"
    IN = "in"
    UPCOMING = "upcoming"
    PREVIOUS = "previous"
    PLUS = "+"
    MINUS = "-"
    STAR = "*"
    SLASH = "/"
    PERCENT = "%"
    AT = "@"
    ASSIGN = "="
    EQ = "=="
    NE = "!="
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="
    LPAREN = "("
    RPAREN = ")"
    COMMA = ","


@dataclass(frozen=True, slots=True)
class ColonLiteral:
    """A colon-separated literal, before anyone has decided what it means.

    ``fields`` holds the written values with ``None`` for an elided leading
    field, so ``::15`` is ``(None, None, 15.0)``.  ``leading`` names the unit
    of the leftmost field.  ``forced_duration`` is set by the two explicit
    forms — a ``h``/``m`` suffix or a leading colon — which cannot be read as
    a time of day.
    """

    fields: tuple[float | None, ...]
    leading: str
    forced_duration: bool


@dataclass(frozen=True, slots=True)
class ClockLiteral:
    """A 12-hour clock reading, already converted to 24-hour fields.

    Unlike a :class:`ColonLiteral` this is unambiguous — ``4p`` can only be a
    time of day — so it needs no resolution.
    """

    hour: int
    minute: int
    second: int
    microsecond: int


@dataclass(frozen=True, slots=True)
class DateTimeLiteral:
    """A written date, optionally with a time and a UTC offset."""

    year: int
    month: int
    day: int
    hour: int = 0
    minute: int = 0
    second: int = 0
    microsecond: int = 0
    offset_minutes: int | None = None
    has_time: bool = False


type TokenValue = Duration | ColonLiteral | ClockLiteral | DateTimeLiteral | float | int | None


@dataclass(frozen=True, slots=True)
class Token:
    kind: TokenKind
    text: str
    start: int
    end: int
    value: TokenValue = None


# Units, longest first, so `ms`/`mo`/`bd` win over `m`/`d`.
_UNITS: Final[tuple[str, ...]] = ("ms", "mo", "bd", "s", "m", "h", "d", "w", "y")
_UNIT_SET: Final = frozenset(_UNITS)

_KEYWORDS: Final[dict[str, TokenKind]] = {
    "now": TokenKind.NOW,
    "today": TokenKind.TODAY,
    "tomorrow": TokenKind.TOMORROW,
    "yesterday": TokenKind.YESTERDAY,
    "in": TokenKind.IN,
    "upcoming": TokenKind.UPCOMING,
    "previous": TokenKind.PREVIOUS,
}

_WEEKDAYS: Final[dict[str, int]] = {
    name: index
    for index, names in enumerate(
        [
            ("monday", "mon"),
            ("tuesday", "tue", "tues"),
            ("wednesday", "wed"),
            ("thursday", "thu", "thur", "thurs"),
            ("friday", "fri"),
            ("saturday", "sat"),
            ("sunday", "sun"),
        ]
    )
    for name in names
}

_TWO_CHAR_OPERATORS: Final[dict[str, TokenKind]] = {
    "==": TokenKind.EQ,
    "!=": TokenKind.NE,
    "<=": TokenKind.LE,
    ">=": TokenKind.GE,
}

_ONE_CHAR_OPERATORS: Final[dict[str, TokenKind]] = {
    "+": TokenKind.PLUS,
    "-": TokenKind.MINUS,
    "*": TokenKind.STAR,
    "/": TokenKind.SLASH,
    "%": TokenKind.PERCENT,
    "@": TokenKind.AT,
    "=": TokenKind.ASSIGN,
    "<": TokenKind.LT,
    ">": TokenKind.GT,
    "(": TokenKind.LPAREN,
    ")": TokenKind.RPAREN,
    ",": TokenKind.COMMA,
}

_MAX_DAY_OF_MONTH: Final = 31
_MAX_COLON_FIELDS: Final = 3

_DATETIME_RE = re.compile(
    r"""
    (?P<date>\d{4}-\d{2}-\d{2})
    (?:
        [T ]
        (?P<hour>\d{1,2}):(?P<minute>\d{2})
        (?::(?P<second>\d{2})(?:\.(?P<fraction>\d+))?)?
        (?P<offset>Z|[+-]\d{2}:\d{2})?
    )?
    """,
    re.VERBOSE,
)
_ORDINAL_RE = re.compile(r"(\d{1,2})(?:st|nd|rd|th)(?![A-Za-z0-9_])")
_MERIDIEM_RE = re.compile(
    r"(\d{1,2})(?::(\d{2}))?(?::(\d{2})(?:\.(\d+))?)?(am|pm|a|p)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
_NUMBER_UNIT_RE = re.compile(r"(\d+(?:\.\d+)?)(" + "|".join(_UNITS) + r")")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_COLON_RUN_RE = re.compile(r"[0-9.:]+")
_WORD_TAIL_RE = re.compile(r"[A-Za-z0-9_]+")


def is_meta_command(line: str) -> bool:
    """True when ``line`` is a REPL command rather than an expression.

    The whole rule: a colon followed by a letter is a command, a colon
    followed by a digit or another colon is the start of a value.  That is
    what lets ``:help`` and ``:12:15`` coexist.
    """
    stripped = line.lstrip()
    return len(stripped) > 1 and stripped[0] == ":" and stripped[1].isalpha()


def tokenize(source: str) -> list[Token]:
    """Scan ``source`` into tokens, or raise :class:`DtcalcError` with a span."""
    tokens: list[Token] = []
    position = 0
    length = len(source)

    while position < length:
        char = source[position]

        if char.isspace():
            position += 1
            continue

        if char == "#":
            # A comment runs to the end of the line.  Useful in piped input
            # and in the golden transcripts, which read better annotated.
            break

        if char == ":" and _starts_colon_literal(source, position):
            token, position = _scan_colon_literal(source, position)
            tokens.append(token)
            continue

        if char.isdigit():
            token, position = _scan_numeric(source, position)
            tokens.append(token)
            continue

        if char.isalpha() or char == "_":
            token, position = _scan_word(source, position)
            tokens.append(token)
            continue

        pair = source[position : position + 2]
        if pair in _TWO_CHAR_OPERATORS:
            tokens.append(Token(_TWO_CHAR_OPERATORS[pair], pair, position, position + 2))
            position += 2
            continue

        if char in _ONE_CHAR_OPERATORS:
            tokens.append(Token(_ONE_CHAR_OPERATORS[char], char, position, position + 1))
            position += 1
            continue

        raise DtcalcError(f"unexpected character {char!r}", position, position + 1)

    return tokens


def _starts_colon_literal(source: str, position: int) -> bool:
    nxt = source[position + 1 : position + 2]
    return nxt.isdigit() or nxt == ":"


# --------------------------------------------------------------------------
# numeric literals
# --------------------------------------------------------------------------


def _scan_numeric(source: str, start: int) -> tuple[Token, int]:
    """Scan whatever a digit can begin, in order of specificity."""
    datetime_token = _try_datetime(source, start)
    if datetime_token is not None:
        return datetime_token

    meridiem = _try_meridiem(source, start)
    if meridiem is not None:
        return meridiem

    run = _COLON_RUN_RE.match(source, start)
    if run is not None and ":" in run.group():
        return _scan_colon_literal(source, start)

    ordinal = _ORDINAL_RE.match(source, start)
    if ordinal is not None:
        day = int(ordinal.group(1))
        if not 1 <= day <= _MAX_DAY_OF_MONTH:
            raise DtcalcError(f"{day} is not a day of the month", start, ordinal.end())
        return Token(TokenKind.ORDINAL, ordinal.group(), start, ordinal.end(), day), ordinal.end()

    duration = _try_duration(source, start)
    if duration is not None:
        return duration

    number = _NUMBER_RE.match(source, start)
    assert number is not None  # a digit always starts a number
    _reject_trailing_word(source, start, number.end())
    return (
        Token(TokenKind.NUMBER, number.group(), start, number.end(), float(number.group())),
        number.end(),
    )


def _try_meridiem(source: str, start: int) -> tuple[Token, int] | None:
    """Scan ``4p``, ``4:30pm`` and friends into a 24-hour clock reading."""
    match = _MERIDIEM_RE.match(source, start)
    if match is None:
        return None

    hour = int(match.group(1))
    if not 1 <= hour <= 12:
        raise DtcalcError(f"{hour} is not an hour on a 12-hour clock", start, match.end())
    minute = int(match.group(2) or 0)
    second = int(match.group(3) or 0)
    fraction = match.group(4) or ""
    microsecond = int(fraction.ljust(6, "0")[:6]) if fraction else 0
    if minute > 59 or second > 59:
        raise DtcalcError(f"{match.group()!r} is not a time of day", start, match.end())

    # 12am is midnight and 12pm is noon, which is the one case worth spelling
    # out: the hour wraps to 0 in the morning and stays 12 in the afternoon.
    is_pm = match.group(5).lower().startswith("p")
    hour = (hour % 12) + (12 if is_pm else 0)

    literal = ClockLiteral(hour, minute, second, microsecond)
    return Token(TokenKind.CLOCK, match.group(), start, match.end(), literal), match.end()


def _try_datetime(source: str, start: int) -> tuple[Token, int] | None:
    match = _DATETIME_RE.match(source, start)
    if match is None:
        return None

    year, month, day = (int(part) for part in match.group("date").split("-"))
    has_time = match.group("hour") is not None
    hour = int(match.group("hour") or 0)
    minute = int(match.group("minute") or 0)
    second = int(match.group("second") or 0)
    fraction = match.group("fraction") or ""
    microsecond = int(fraction.ljust(6, "0")[:6]) if fraction else 0

    try:
        datetime(year, month, day, hour, minute, second, microsecond)
    except ValueError as exc:
        raise DtcalcError(
            f"{match.group()!r} is not a real date and time: {exc}", start, match.end()
        ) from exc

    literal = DateTimeLiteral(
        year=year,
        month=month,
        day=day,
        hour=hour,
        minute=minute,
        second=second,
        microsecond=microsecond,
        offset_minutes=_parse_offset(match.group("offset")),
        has_time=has_time,
    )
    kind = TokenKind.DATETIME if has_time else TokenKind.DATE
    return Token(kind, match.group(), start, match.end(), literal), match.end()


def _parse_offset(offset: str | None) -> int | None:
    if offset is None:
        return None
    if offset == "Z":
        return 0
    sign = -1 if offset[0] == "-" else 1
    hours, minutes = (int(part) for part in offset[1:].split(":"))
    return sign * (hours * 60 + minutes)


def _try_duration(source: str, start: int) -> tuple[Token, int] | None:
    position = start
    counts: dict[str, float] = {}
    while (match := _NUMBER_UNIT_RE.match(source, position)) is not None:
        amount, unit = float(match.group(1)), match.group(2)
        counts[unit] = counts.get(unit, 0.0) + amount
        position = match.end()

    if position == start:
        return None

    _reject_trailing_word(source, start, position)
    text = source[start:position]
    return Token(TokenKind.DURATION, text, start, position, Duration.build(**counts)), position


def _reject_trailing_word(source: str, start: int, end: int) -> None:
    """Refuse ``5hfoo``: a literal may not run straight into a word."""
    tail = _WORD_TAIL_RE.match(source, end)
    if tail is not None:
        raise DtcalcError(
            f"{source[start : tail.end()]!r} is not a valid literal", start, tail.end()
        )


# --------------------------------------------------------------------------
# colon literals
# --------------------------------------------------------------------------


def _scan_colon_literal(source: str, start: int) -> tuple[Token, int]:
    run = _COLON_RUN_RE.match(source, start)
    assert run is not None  # callers check for a digit or colon
    end = run.end()
    raw = run.group()

    suffix = source[end : end + 1]
    if suffix in {"h", "m"}:
        # `12:15ms` and friends: the suffix names the *leading* unit, so a
        # two-letter unit here is a mistake rather than a longer suffix.
        tail = _WORD_TAIL_RE.match(source, end)
        assert tail is not None
        if tail.end() != end + 1:
            raise DtcalcError(
                f"a colon literal's leading unit must be 'h' or 'm', not "
                f"{source[end : tail.end()]!r}",
                start,
                tail.end(),
            )
        end += 1
    elif suffix.isalpha():
        tail = _WORD_TAIL_RE.match(source, end)
        assert tail is not None
        raise DtcalcError(
            f"a colon literal's leading unit must be 'h' or 'm', not {source[end : tail.end()]!r}",
            start,
            tail.end(),
        )
    else:
        suffix = ""

    literal = _parse_colon_fields(raw, suffix, start, end, source)
    return Token(TokenKind.COLON_LITERAL, source[start:end], start, end, literal), end


def _parse_colon_fields(raw: str, suffix: str, start: int, end: int, source: str) -> ColonLiteral:
    parts = raw.split(":")
    if len(parts) > _MAX_COLON_FIELDS:
        raise DtcalcError(
            f"too many fields in {raw!r}: a colon literal has at most three", start, end
        )

    seen_value = False
    fields: list[float | None] = []
    for part in parts:
        if part:
            seen_value = True
            fields.append(_parse_colon_field(part, raw, start, end))
        elif seen_value:
            raise DtcalcError(
                f"{raw!r} has a gap: only the leading fields may be left out", start, end
            )
        else:
            fields.append(None)

    if not seen_value:
        raise DtcalcError(f"{raw!r} has no digits", start, end)

    leading = suffix if suffix == "m" else "h"
    available = _MAX_COLON_FIELDS if leading == "h" else _MAX_COLON_FIELDS - 1
    if len(fields) > available:
        raise DtcalcError(
            f"too many fields in {source[start:end]!r}: counting from {leading!r} "
            f"there are only {available} units to fill",
            start,
            end,
        )

    return ColonLiteral(tuple(fields), leading, bool(suffix) or raw.startswith(":"))


def _parse_colon_field(part: str, raw: str, start: int, end: int) -> float:
    try:
        return float(part)
    except ValueError as exc:
        raise DtcalcError(f"{part!r} is not a number in {raw!r}", start, end) from exc


# --------------------------------------------------------------------------
# words
# --------------------------------------------------------------------------


def _scan_word(source: str, start: int) -> tuple[Token, int]:
    match = _IDENT_RE.match(source, start)
    assert match is not None  # caller checked for a letter or underscore
    text = match.group()
    end = match.end()
    lowered = text.lower()

    if lowered in _KEYWORDS:
        return Token(_KEYWORDS[lowered], text, start, end), end
    if lowered in _WEEKDAYS:
        return Token(TokenKind.WEEKDAY, text, start, end, _WEEKDAYS[lowered]), end
    if lowered in _UNIT_SET:
        raise DtcalcError(
            f"{text!r} is a unit, not a name; units need a number in front of them",
            start,
            end,
        )
    return Token(TokenKind.IDENT, text, start, end), end
