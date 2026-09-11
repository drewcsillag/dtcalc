"""The tree-walking evaluator.

``now`` is read from the clock exactly once per line and reused, so that
``now == now`` is true and ``now - now`` is zero even on a real clock.
"""

from __future__ import annotations

import calendar
from collections.abc import Callable
from datetime import date as StdDate
from datetime import datetime, time, timedelta, timezone
from typing import Final, assert_never
from zoneinfo import ZoneInfo

from dtcalc.ast import (
    Assign,
    Attach,
    Binary,
    Call,
    Convert,
    DateAtTime,
    DateTimeLit,
    DayKeyword,
    DurationLit,
    Negate,
    Node,
    NowLit,
    NumberLit,
    OrdinalRef,
    TimeOfDay,
    VarRef,
    WeekdayRef,
)
from dtcalc.date import Date
from dtcalc.duration import Duration
from dtcalc.env import Env
from dtcalc.errors import DtcalcError
from dtcalc.functions import call_builtin
from dtcalc.instant import Instant
from dtcalc.parser import parse
from dtcalc.resolve import resolve
from dtcalc.values import Boolean, Number, Value
from dtcalc.zones import resolve_zone

__all__ = ["evaluate", "evaluate_line"]

_DAYS_PER_WEEK: Final = 7
# A day of the month can be missing from at most a couple of months in a row,
# but the loop is bounded anyway so a bad input cannot spin forever.
_MAX_MONTHS_SEARCHED: Final = 120


def evaluate_line(source: str, env: Env) -> Value:
    """Parse, resolve and evaluate one line, updating ``env`` for assignments."""
    tree = resolve(parse(source), env.types())
    return evaluate(tree, env)


def evaluate(node: Node, env: Env) -> Value:
    return _Evaluator(env).run(node)


class _Evaluator:
    def __init__(self, env: Env) -> None:
        self._env = env
        # One reading of the clock for the whole line.
        self._now = env.clock.now()

    # ------------------------------------------------------------------

    def run(self, node: Node) -> Value:
        match node:
            case NumberLit(value=value):
                return Number(value)

            case DurationLit(duration=duration):
                return duration

            case NowLit():
                return Instant(self._now, self._env.zone)

            case TimeOfDay():
                return self._at_time(self._today(), node)

            case DayKeyword(offset_days=offset):
                return self._midnight(self._today() + timedelta(days=offset))

            case WeekdayRef(direction=direction, weekday=weekday):
                return self._midnight(self._weekday_date(direction, weekday))

            case OrdinalRef(direction=direction, day=day):
                return self._midnight(self._ordinal_date(direction, day, node))

            case DateAtTime(date=date_node, time=time_node):
                base = self.run(date_node)
                assert isinstance(base, Instant)
                assert isinstance(time_node, TimeOfDay)
                return self._at_time(base.wall_clock().date(), time_node)

            case DateTimeLit():
                return self._datetime_literal(node)

            case VarRef(name=name):
                stored = self._env.variables.get(name)
                if stored is None:
                    raise DtcalcError(f"undefined variable {name!r}", node.start, node.end)
                return stored

            case Assign(name=name, value=value_node):
                assigned = self.run(value_node)
                self._env.variables[name] = assigned
                return assigned

            case Negate(operand=operand):
                inner = self.run(operand)
                if isinstance(inner, Duration):
                    return -inner
                if isinstance(inner, Number):
                    return Number(-inner.value)
                raise DtcalcError(f"cannot negate {_describe(inner)}", node.start, node.end)

            case Convert(operand=operand, zone_name=zone_name):
                target = self.run(operand)
                if not isinstance(target, Instant):
                    raise DtcalcError(
                        f"can only convert an instant to another zone, not {_describe(target)}",
                        node.start,
                        node.end,
                    )
                return target.convert_to(self._zone(zone_name, node))

            case Attach(operand=operand, zone_name=zone_name):
                subject = self.run(operand)
                if not isinstance(subject, Instant):
                    raise DtcalcError(
                        f"can only attach a zone to an instant, not {_describe(subject)}",
                        node.start,
                        node.end,
                    )
                return subject.attach(self._zone(zone_name, node))

            case Binary(op=op, left=left, right=right):
                return _binary(op, self.run(left), self.run(right), node)

            case Call(name=name, args=args):
                return call_builtin(name, tuple(self.run(arg) for arg in args), node, self._env)

            case _:  # pragma: no cover - every node type is covered above
                raise AssertionError(f"unhandled node {node!r}")

    # ------------------------------------------------------------------
    # dates and times
    # ------------------------------------------------------------------

    def _today(self) -> StdDate:
        return self._now.astimezone(self._env.zone).date()

    def _midnight(self, day: StdDate) -> Instant:
        return Instant.from_wall_clock(self._env.zone, datetime.combine(day, time()), strict=False)

    def _at_time(self, day: StdDate, reading: TimeOfDay) -> Instant:
        wall = datetime.combine(
            day,
            time(reading.hour, reading.minute, reading.second, reading.microsecond),
        )
        return Instant.from_wall_clock(self._env.zone, wall, strict=False)

    def _weekday_date(self, direction: str, weekday: int) -> StdDate:
        """The nearest such weekday, strictly after or before today.

        Strictly: asking for ``upcoming friday`` on a Friday gives next week's,
        because ``today`` already names today.
        """
        today = self._today()
        if direction == "upcoming":
            delta = (weekday - today.weekday()) % _DAYS_PER_WEEK or _DAYS_PER_WEEK
            return today + timedelta(days=delta)
        delta = (today.weekday() - weekday) % _DAYS_PER_WEEK or _DAYS_PER_WEEK
        return today - timedelta(days=delta)

    def _ordinal_date(self, direction: str, day: int, node: Node) -> StdDate:
        """The nearest such day of the month, strictly after or before today.

        Months that do not have the day are skipped, so the next 31st after
        31 January is 31 March.
        """
        today = self._today()
        step = 1 if direction == "upcoming" else -1
        year, month = today.year, today.month
        for _ in range(_MAX_MONTHS_SEARCHED):
            if day <= calendar.monthrange(year, month)[1]:
                candidate = StdDate(year, month, day)
                if (candidate > today) if step > 0 else (candidate < today):
                    return candidate
            month += step
            if month > 12:
                year, month = year + 1, 1
            elif month < 1:
                year, month = year - 1, 12
            if not 1 <= year <= 9999:
                break
        raise DtcalcError(
            f"no {direction} day {day} of the month is in range", node.start, node.end
        )

    def _datetime_literal(self, node: DateTimeLit) -> Instant:
        literal = node.literal
        naive = datetime(
            literal.year,
            literal.month,
            literal.day,
            literal.hour,
            literal.minute,
            literal.second,
            literal.microsecond,
        )
        if literal.offset_minutes is not None:
            fixed = naive.replace(tzinfo=timezone(timedelta(minutes=literal.offset_minutes)))
            return Instant(fixed, self._env.zone)
        # A typed literal is strict: a wall-clock time that does not exist, or
        # one that happens twice, is a mistake the user wants to hear about —
        # with the offending literal underlined.
        try:
            return Instant.from_wall_clock(self._env.zone, naive, strict=True)
        except DtcalcError as exc:
            raise DtcalcError(exc.message, node.start, node.end) from exc

    def _zone(self, name: str, node: Node) -> ZoneInfo:
        try:
            return resolve_zone(name)
        except DtcalcError as exc:
            raise DtcalcError(exc.message, node.start, node.end) from exc


# --------------------------------------------------------------------------
# binary operators
# --------------------------------------------------------------------------

_COMPARISONS: Final = {"<", "<=", ">", ">=", "==", "!="}


def _describe(value: Value) -> str:
    """A value's kind, for error messages.

    Exhaustive over the ``Value`` union by ``assert_never``, so a new value
    type cannot reach a user as "a <unknown>".
    """
    match value:
        case Date():
            return "a date"
        case Instant():
            return "an instant"
        case Duration():
            return "a duration"
        case Number():
            return "a number"
        case Boolean():
            return "a boolean"
        case _ as unhandled:
            assert_never(unhandled)


def _binary(op: str, left: Value, right: Value, node: Node) -> Value:
    if op in _COMPARISONS:
        return Boolean(_compare(op, left, right, node))
    if op == "+":
        return _add(left, right, node)
    if op == "-":
        return _subtract(left, right, node)
    if op == "*":
        return _multiply(left, right, node)
    if op == "/":
        return _divide(left, right, node)
    return _modulo(left, right, node)


def _add(left: Value, right: Value, node: Node) -> Value:
    match left, right:
        case Instant(), Duration():
            return left + right
        case Duration(), Instant():
            return right + left
        case Duration(), Duration():
            return left + right
        case Number(), Number():
            return Number(left.value + right.value)
        case Instant(), Instant():
            raise DtcalcError(
                "cannot add two instants; subtract them to get the time between",
                node.start,
                node.end,
            )
        case _:
            raise DtcalcError(
                f"cannot add {_describe(right)} to {_describe(left)}; "
                f"adding to an instant needs a duration",
                node.start,
                node.end,
            )


def _subtract(left: Value, right: Value, node: Node) -> Value:
    match left, right:
        case Instant(), Duration():
            return left - right
        case Instant(), Instant():
            return left.elapsed_since(right)
        case Duration(), Duration():
            return left - right
        case Number(), Number():
            return Number(left.value - right.value)
        case _:
            raise DtcalcError(
                f"cannot subtract {_describe(right)} from {_describe(left)}",
                node.start,
                node.end,
            )


def _multiply(left: Value, right: Value, node: Node) -> Value:
    match left, right:
        case Duration(), Number():
            return _wrap(lambda: left * right.value, node)
        case Number(), Duration():
            return _wrap(lambda: right * left.value, node)
        case Number(), Number():
            return Number(left.value * right.value)
        case _:
            raise DtcalcError(
                f"cannot multiply {_describe(left)} by {_describe(right)}",
                node.start,
                node.end,
            )


def _divide(left: Value, right: Value, node: Node) -> Value:
    match left, right:
        case Duration(), Number():
            return _wrap(lambda: left / right.value, node)
        case Duration(), Duration():
            return _wrap(lambda: Number(left.divide_by(right)), node)
        case Number(), Number():
            if right.value == 0:
                raise DtcalcError("cannot divide by zero", node.start, node.end)
            return Number(left.value / right.value)
        case _:
            raise DtcalcError(
                f"cannot divide {_describe(left)} by {_describe(right)}",
                node.start,
                node.end,
            )


def _modulo(left: Value, right: Value, node: Node) -> Value:
    if isinstance(left, Duration) and isinstance(right, Duration):
        return _wrap(lambda: left % right, node)
    raise DtcalcError(
        f"cannot take {_describe(left)} modulo {_describe(right)}", node.start, node.end
    )


def _compare(op: str, left: Value, right: Value, node: Node) -> bool:
    order = _ordering(left, right, node)
    match op:
        case "<":
            return order < 0
        case "<=":
            return order <= 0
        case ">":
            return order > 0
        case ">=":
            return order >= 0
        case "==":
            return order == 0
        case _:
            return order != 0


def _ordering(left: Value, right: Value, node: Node) -> int:
    match left, right:
        case Instant(), Instant():
            return _sign((left.moment > right.moment) - (left.moment < right.moment))
        case Duration(), Duration():
            try:
                return left.compare(right)
            except DtcalcError as exc:
                raise DtcalcError(exc.message, node.start, node.end) from exc
        case Number(), Number():
            return _sign((left.value > right.value) - (left.value < right.value))
        case Boolean(), Boolean():
            return _sign(int(left.value) - int(right.value))
        case _:
            raise DtcalcError(
                f"cannot compare {_describe(left)} with {_describe(right)}",
                node.start,
                node.end,
            )


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


def _wrap[T](operation: Callable[[], T], node: Node) -> T:
    """Run a value-level operation, re-raising its error with a source span.

    Duration arithmetic does not know where it came from, so the span is
    attached here where the expression node is in hand.
    """
    try:
        return operation()
    except DtcalcError as exc:
        raise DtcalcError(exc.message, node.start, node.end) from exc
