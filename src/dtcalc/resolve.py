"""Deciding what a colon literal means.

``12:15`` is twelve hours and fifteen minutes in one place and a quarter past
noon in another, and no amount of grammar settles which.  This pass walks the
tree with an *expectation* — what the surrounding operator can accept — and
rewrites every :class:`~dtcalc.ast.ColonLit` into either a
:class:`~dtcalc.ast.TimeOfDay` or a :class:`~dtcalc.ast.DurationLit`.

Two rules do the work:

* Where only one reading typechecks, that reading wins.  ``<instant> - 12:15``
  must be a duration; ``12:13 in Tokyo`` must be a clock reading.
* Where both typecheck, the clock reading wins.  ``12:15 + 3h`` is a quarter
  past noon plus three hours, on the grounds that a duration is more naturally
  written ``12h15m`` anyway.

It needs the variable environment, because ``12:15 + foo`` depends on what
``foo`` is.  Variables are eager, so that is always known by evaluation time.
This is also where the type errors that can be proved without running
anything are raised.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from dtcalc.ast import (
    Assign,
    Attach,
    Binary,
    Call,
    ColonLit,
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
from dtcalc.builtins import SIGNATURES, Expect, Kind
from dtcalc.duration import Duration
from dtcalc.errors import DtcalcError
from dtcalc.lexer import ColonLiteral

__all__ = ["Expect", "Kind", "resolve"]

# Units in descending order, so a literal's leading unit picks a slice.
_UNIT_ORDER: Final[tuple[str, ...]] = ("h", "m", "s")

_MAX_HOUR: Final = 23
_MAX_MINUTE: Final = 59
_MAX_SECOND: Final = 60  # exclusive; leap seconds are not represented

type Types = Mapping[str, Kind]


def resolve(node: Node, types: Types) -> Node:
    """Return an equivalent tree with every colon literal decided."""
    return _resolve(node, Expect.EITHER, types)


# --------------------------------------------------------------------------
# kind inference
# --------------------------------------------------------------------------


def _infer(node: Node, types: Types) -> Kind | None:
    """The kind of ``node``, or ``None`` when a colon literal makes it ambiguous."""
    match node:
        case NumberLit():
            return Kind.NUMBER
        case DurationLit():
            return Kind.DURATION
        case ColonLit(literal=literal):
            return Kind.DURATION if literal.forced_duration else None
        case (
            TimeOfDay()
            | DateTimeLit()
            | NowLit()
            | DayKeyword()
            | WeekdayRef()
            | OrdinalRef()
            | DateAtTime()
            | Attach()
            | Convert()
        ):
            return Kind.INSTANT
        case VarRef(name=name):
            return _lookup(node, name, types)
        case Assign(value=value):
            return _infer(value, types)
        case Negate(operand=operand):
            return _infer(operand, types)
        case Binary(op=op, left=left, right=right):
            return _infer_binary(op, _infer(left, types), _infer(right, types))
        case Call(name=name, args=args):
            signature = SIGNATURES.get(name)
            if signature is None:
                return None
            if signature.returns is not None:
                return signature.returns
            return _infer(args[0], types) if args else None
        case _:  # pragma: no cover - every node type is covered above
            raise AssertionError(f"unhandled node {node!r}")


def _infer_binary(op: str, left: Kind | None, right: Kind | None) -> Kind | None:
    if op in {"<", "<=", ">", ">=", "==", "!="}:
        return Kind.BOOLEAN
    if op == "+":
        if Kind.INSTANT in (left, right):
            return Kind.INSTANT
        return Kind.DURATION
    if op == "-":
        if left is Kind.INSTANT:
            return Kind.DURATION if right is Kind.INSTANT else Kind.INSTANT
        return Kind.DURATION
    if op == "*":
        return Kind.NUMBER if left is Kind.NUMBER and right is Kind.NUMBER else Kind.DURATION
    if op == "/":
        if left is Kind.DURATION and right is Kind.DURATION:
            return Kind.NUMBER
        return Kind.DURATION if left is Kind.DURATION else Kind.NUMBER
    return Kind.DURATION  # '%'


def _lookup(node: Node, name: str, types: Types) -> Kind:
    kind = types.get(name)
    if kind is None:
        raise DtcalcError(f"undefined variable {name!r}", node.start, node.end)
    return kind


# --------------------------------------------------------------------------
# the pass itself
# --------------------------------------------------------------------------


def _resolve(node: Node, expect: Expect, types: Types) -> Node:
    match node:
        case ColonLit():
            return _decide(node, expect)

        case NumberLit() | DurationLit() | TimeOfDay() | DateTimeLit() | NowLit():
            return node

        case DayKeyword() | WeekdayRef() | OrdinalRef():
            return node

        case VarRef(name=name):
            _lookup(node, name, types)
            return node

        case DateAtTime(date=date, time=time):
            # A date narrowed by a clock reading.  The time is never a
            # duration; the date side may be any instant expression, since
            # `foo @ 4p` reaches here as well as `today 09:00`.
            return DateAtTime(
                node.start,
                node.end,
                _require_instant(date, "take the date from", types),
                _resolve(time, Expect.INSTANT, types),
            )

        case Assign(name=name, value=value):
            if name in SIGNATURES:
                raise DtcalcError(
                    f"{name!r} is a builtin function, so it cannot be a variable name",
                    node.start,
                    node.end,
                )
            return Assign(node.start, node.end, name, _resolve(value, expect, types))

        case Negate(operand=operand):
            if _infer(operand, types) is Kind.INSTANT:
                raise DtcalcError("cannot negate an instant", node.start, node.end)
            return Negate(node.start, node.end, _resolve(operand, Expect.DURATION, types))

        case Convert(operand=operand, zone_name=zone):
            return Convert(node.start, node.end, _require_instant(operand, "convert", types), zone)

        case Attach(operand=operand, zone_name=zone):
            return Attach(
                node.start, node.end, _require_instant(operand, "attach a zone to", types), zone
            )

        case Binary(op=op, left=left, right=right):
            return _resolve_binary(node, op, left, right, types)

        case Call(name=name, args=args):
            return _resolve_call(node, name, args, types)

        case _:  # pragma: no cover - every node type is covered above
            raise AssertionError(f"unhandled node {node!r}")


def _require_instant(operand: Node, verb: str, types: Types) -> Node:
    kind = _infer(operand, types)
    if kind is not None and kind is not Kind.INSTANT:
        raise DtcalcError(f"can only {verb} an instant, not a {kind}", operand.start, operand.end)
    return _resolve(operand, Expect.INSTANT, types)


def _resolve_binary(node: Node, op: str, left: Node, right: Node, types: Types) -> Node:
    left_kind = _infer(left, types)
    right_kind = _infer(right, types)
    left_expect, right_expect = _operand_expectations(node, op, left_kind, right_kind)
    return Binary(
        node.start,
        node.end,
        op,
        _resolve(left, left_expect, types),
        _resolve(right, right_expect, types),
    )


def _operand_expectations(
    node: Node, op: str, left: Kind | None, right: Kind | None
) -> tuple[Expect, Expect]:
    """Work out what each side of a binary operator can accept."""
    if op in {"*", "/", "%"}:
        # Only durations and numbers take part; a clock reading is meaningless.
        return Expect.DURATION, Expect.DURATION

    if op == "+":
        if left is Kind.INSTANT and right is Kind.INSTANT:
            raise DtcalcError(
                "cannot add two instants; subtract them to get the time between",
                node.start,
                node.end,
            )
        if left is Kind.INSTANT:
            return Expect.INSTANT, Expect.DURATION
        if right is Kind.INSTANT:
            return Expect.DURATION, Expect.INSTANT
        if left is None and right is None:
            # `12:15 + 12:15`: read the first as a time and the second as a
            # duration, which is the only combination that typechecks.
            return Expect.EITHER, Expect.DURATION
        return Expect.EITHER, Expect.DURATION

    if op == "-":
        if left is Kind.INSTANT:
            # `<instant> - 12:15` is the original request's example: a
            # duration, not "the time between noon and a quarter past".
            return Expect.INSTANT, Expect.DURATION
        if right is Kind.INSTANT:
            return Expect.INSTANT, Expect.INSTANT
        if left is Kind.DURATION:
            return Expect.DURATION, Expect.DURATION
        return Expect.EITHER, Expect.DURATION

    # Comparisons: both sides must be the same kind, so a known side decides.
    if left is Kind.INSTANT or right is Kind.INSTANT:
        return Expect.INSTANT, Expect.INSTANT
    if left is Kind.DURATION or right is Kind.DURATION:
        return Expect.DURATION, Expect.DURATION
    return Expect.EITHER, Expect.EITHER


def _resolve_call(node: Node, name: str, args: tuple[Node, ...], types: Types) -> Node:
    signature = SIGNATURES.get(name)
    if signature is None:
        known = ", ".join(sorted(SIGNATURES))
        raise DtcalcError(
            f"unknown function {name!r}; the ones there are: {known}", node.start, node.end
        )

    count = len(args)
    if count < signature.min_args or (
        signature.max_args is not None and count > signature.max_args
    ):
        raise DtcalcError(
            f"{name} takes {_describe_arity(signature.min_args, signature.max_args)} "
            f"but was given {count}",
            node.start,
            node.end,
        )

    resolved = tuple(
        _resolve(arg, signature.expectation(position), types) for position, arg in enumerate(args)
    )
    return Call(node.start, node.end, name, resolved)


def _describe_arity(minimum: int, maximum: int | None) -> str:
    if maximum is None:
        return f"at least {minimum} argument{'s' if minimum != 1 else ''}"
    if minimum == maximum:
        return f"{minimum} argument{'s' if minimum != 1 else ''}"
    return f"{minimum} to {maximum} arguments"


# --------------------------------------------------------------------------
# turning a colon literal into one thing or the other
# --------------------------------------------------------------------------


def _decide(node: ColonLit, expect: Expect) -> Node:
    literal = node.literal

    if literal.forced_duration:
        if expect is Expect.INSTANT:
            raise DtcalcError(
                f"{node.text!r} is a duration, not a time of day", node.start, node.end
            )
        return DurationLit(node.start, node.end, _as_duration(literal))

    if expect is Expect.DURATION:
        return DurationLit(node.start, node.end, _as_duration(literal))

    if expect is Expect.NUMBER:
        raise DtcalcError(
            f"expected a number, but {node.text!r} is a time or a duration",
            node.start,
            node.end,
        )

    # Expect.INSTANT, and the tie-break for Expect.EITHER.
    return _as_time_of_day(node)


def _as_duration(literal: ColonLiteral) -> Duration:
    """Assign the fields to units, counting down from the leading one."""
    start = _UNIT_ORDER.index(literal.leading)
    units = _UNIT_ORDER[start : start + len(literal.fields)]
    counts = {
        unit: value for unit, value in zip(units, literal.fields, strict=True) if value is not None
    }
    return Duration.build(**counts)


def _as_time_of_day(node: ColonLit) -> TimeOfDay:
    literal = node.literal
    values = [0.0 if field is None else field for field in literal.fields]
    while len(values) < 3:
        values.append(0.0)
    hour, minute, second = values

    valid = (
        float(hour).is_integer()
        and float(minute).is_integer()
        and 0 <= hour <= _MAX_HOUR
        and 0 <= minute <= _MAX_MINUTE
        and 0 <= second < _MAX_SECOND
    )
    if not valid:
        raise DtcalcError(f"{node.text!r} is not a time of day", node.start, node.end)

    whole = int(second)
    microsecond = round((second - whole) * 1_000_000)
    return TimeOfDay(node.start, node.end, int(hour), int(minute), whole, microsecond)
