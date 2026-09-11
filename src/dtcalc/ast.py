"""The abstract syntax tree.

Two node types deserve a word.

:class:`ColonLit` is a colon literal the parser has *not* interpreted.
Whether ``12:15`` is twelve hours fifteen minutes or a quarter past noon
depends on what surrounds it, and in the general case on the type of a
variable, so the decision belongs to :mod:`dtcalc.resolve`.

:class:`TimeOfDay` is what a :class:`ColonLit` becomes when resolution decides
it names a clock reading; :class:`DurationLit` is what it becomes otherwise.
So a resolved tree contains no :class:`ColonLit` at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from dtcalc.duration import Duration
from dtcalc.lexer import ColonLiteral, DateTimeLiteral
from dtcalc.values import format_number

__all__ = [
    "Assign",
    "Attach",
    "Binary",
    "Call",
    "ColonLit",
    "Convert",
    "DateAtTime",
    "DateTimeLit",
    "DayKeyword",
    "DurationLit",
    "Negate",
    "Node",
    "NowLit",
    "NumberLit",
    "OrdinalRef",
    "TimeOfDay",
    "VarRef",
    "WeekdayRef",
    "sexpr",
]

WEEKDAY_NAMES: Final = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


@dataclass(frozen=True, slots=True)
class Node:
    """Base class carrying the source span, for error reporting."""

    start: int
    end: int


@dataclass(frozen=True, slots=True)
class NumberLit(Node):
    value: float


@dataclass(frozen=True, slots=True)
class DurationLit(Node):
    duration: Duration


@dataclass(frozen=True, slots=True)
class ColonLit(Node):
    """An unresolved colon literal.  ``text`` is kept for error messages."""

    literal: ColonLiteral
    text: str


@dataclass(frozen=True, slots=True)
class TimeOfDay(Node):
    """A clock reading, to be placed on a date by the evaluator."""

    hour: int
    minute: int
    second: int
    microsecond: int


@dataclass(frozen=True, slots=True)
class DateTimeLit(Node):
    literal: DateTimeLiteral
    text: str


@dataclass(frozen=True, slots=True)
class NowLit(Node):
    pass


@dataclass(frozen=True, slots=True)
class DayKeyword(Node):
    """``today``, ``tomorrow`` or ``yesterday``, as an offset in days."""

    name: str
    offset_days: int


@dataclass(frozen=True, slots=True)
class WeekdayRef(Node):
    direction: str  # "upcoming" or "previous"
    weekday: int


@dataclass(frozen=True, slots=True)
class OrdinalRef(Node):
    direction: str  # "upcoming" or "previous"
    day: int


@dataclass(frozen=True, slots=True)
class DateAtTime(Node):
    """A day expression narrowed to a clock reading: ``upcoming friday 09:00``."""

    date: Node
    time: Node


@dataclass(frozen=True, slots=True)
class VarRef(Node):
    name: str


@dataclass(frozen=True, slots=True)
class Assign(Node):
    name: str
    value: Node


@dataclass(frozen=True, slots=True)
class Negate(Node):
    operand: Node


@dataclass(frozen=True, slots=True)
class Binary(Node):
    op: str
    left: Node
    right: Node


@dataclass(frozen=True, slots=True)
class Attach(Node):
    """``expr @ zone`` — read the wall clock as being in ``zone``."""

    operand: Node
    zone_name: str


@dataclass(frozen=True, slots=True)
class Convert(Node):
    """``expr in zone`` — same instant, rendered in ``zone``."""

    operand: Node
    zone_name: str


@dataclass(frozen=True, slots=True)
class Call(Node):
    name: str
    args: tuple[Node, ...]


def _ordinal(day: int) -> str:
    if 11 <= day % 100 <= 13:
        return f"{day}th"
    return f"{day}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th') }"


def sexpr(node: Node) -> str:
    """Render a tree as a compact s-expression, for tests and ``--dump-ast``."""
    match node:
        case NumberLit(value=value):
            return format_number(value)
        case DurationLit(duration=duration):
            return str(duration)
        case ColonLit(text=text):
            return f"colon({text})"
        case TimeOfDay(hour=h, minute=m, second=s, microsecond=us):
            fraction = f".{us:06d}".rstrip("0") if us else ""
            return f"tod({h:02d}:{m:02d}:{s:02d}{fraction})"
        case DateTimeLit(text=text):
            return f"dt({text})"
        case NowLit():
            return "now"
        case DayKeyword(name=name):
            return name
        case WeekdayRef(direction=direction, weekday=weekday):
            return f"{direction}({WEEKDAY_NAMES[weekday]})"
        case OrdinalRef(direction=direction, day=day):
            return f"{direction}({_ordinal(day)})"
        case DateAtTime(date=date, time=time):
            return f"(at {sexpr(date)} {sexpr(time)})"
        case VarRef(name=name):
            return name
        case Assign(name=name, value=value):
            return f"(= {name} {sexpr(value)})"
        case Negate(operand=operand):
            return f"(neg {sexpr(operand)})"
        case Binary(op=op, left=left, right=right):
            return f"({op} {sexpr(left)} {sexpr(right)})"
        case Attach(operand=operand, zone_name=zone):
            return f"(@ {sexpr(operand)} {zone})"
        case Convert(operand=operand, zone_name=zone):
            return f"(in {sexpr(operand)} {zone})"
        case Call(name=name, args=args):
            rendered = " ".join(sexpr(arg) for arg in args)
            return f"({name} {rendered})"
        case _:  # pragma: no cover - every node type is covered above
            raise AssertionError(f"unhandled node {node!r}")
