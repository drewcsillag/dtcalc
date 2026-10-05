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

One case is too close to call and is refused instead: ``2:11 - 1:29`` with two
bare colon literals might be a time of day less a duration or two durations.
:class:`AmbiguousColonError` asks the user to say which, either by rewriting
the line or, in a front end that can ask, by supplying a *choice* for that
operator's span.

It needs the variable environment, because ``12:15 + foo`` depends on what
``foo`` is.  Variables are eager, so that is always known by evaluation time.
This is also where the type errors that can be proved without running
anything are raised.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Literal

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

__all__ = ["AmbiguousColonError", "Choice", "Choices", "Expect", "Kind", "resolve"]

# Units in descending order, so a literal's leading unit picks a slice.
_UNIT_ORDER: Final[tuple[str, ...]] = ("h", "m", "s")

_MAX_HOUR: Final = 23
_MAX_MINUTE: Final = 59
_MAX_SECOND: Final = 60  # exclusive; leap seconds are not represented

type Types = Mapping[str, Kind]

# How to read an ambiguous `colon op colon`: a time of day and a duration, or
# two durations.
type Choice = Literal["clock", "duration"]

# A choice per ambiguous operator, keyed by that operator's span in the source.
type Choices = Mapping[tuple[int, int], Choice]


class AmbiguousColonError(DtcalcError):
    """Two bare colon literals around ``+`` or ``-``, which read either way.

    Carries both explicit spellings so a front end can offer them, and the
    operator's span, which is the key under which a choice is supplied.
    """

    def __init__(self, node: Binary, left: ColonLit, right: ColonLit) -> None:
        self.clock_spelling = f"{left.text} {node.op} {right.text}h"
        self.duration_spelling = f"{left.text}h {node.op} {right.text}"
        self.op = node.op
        self.left_duration = str(_as_duration(left.literal))
        self.right_duration = str(_as_duration(right.literal))
        operation = "plus" if node.op == "+" else "less"
        super().__init__(
            f"{left.text} {node.op} {right.text} is ambiguous: a time of day {operation} "
            "a duration, or two durations",
            node.start,
            node.end,
        )

    @property
    def span(self) -> tuple[int, int]:
        assert self.start is not None and self.end is not None
        return self.start, self.end

    def render(self, line: str) -> str:
        return "\n".join(
            [
                super().render(line),
                f"  as a time of day and a duration: {self.clock_spelling}",
                f"  as two durations ({self.left_duration} {self.op} {self.right_duration}): "
                f"{self.duration_spelling}",
            ]
        )


def resolve(node: Node, types: Types, choices: Choices | None = None) -> Node:
    """Return an equivalent tree with every colon literal decided.

    ``choices`` settles ambiguous operators that would otherwise raise
    :class:`AmbiguousColonError`.
    """
    return _resolve(node, Expect.EITHER, types, choices or {})


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
        case DateTimeLit(literal=literal):
            # The lexer already told us which it is.
            return Kind.INSTANT if literal.has_time else Kind.DATE
        case DayKeyword() | WeekdayRef() | OrdinalRef():
            return Kind.DATE
        case ColonLit(literal=literal):
            return Kind.DURATION if literal.forced_duration else None
        case TimeOfDay() | NowLit() | DateAtTime() | Attach() | Convert():
            # Naming a time or a zone always lands on an instant, including
            # when the thing named was a date.
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


# Kinds that denote a point on the calendar, and so behave alike for every
# decision resolution makes.
_MOMENTS: Final = (Kind.DATE, Kind.INSTANT)


def _article(kind: Kind) -> str:
    """``an instant``, ``a date``. Hardcoding "a" produced "a instant"."""
    return f"an {kind}" if str(kind)[0] in "aeiou" else f"a {kind}"


def _infer_binary(op: str, left: Kind | None, right: Kind | None) -> Kind | None:
    if op in {"<", "<=", ">", ">=", "==", "!="}:
        return Kind.BOOLEAN
    if op == "+":
        # `date + duration` is a date or an instant depending on the
        # duration's *value*, which static inference cannot see. Answering
        # INSTANT is safe rather than a guess: every decision this inference
        # feeds -- colon-literal resolution, the provable type errors --
        # treats dates and instants identically, and the evaluator applies
        # the real rule.
        if left in _MOMENTS or right in _MOMENTS:
            return Kind.INSTANT
        return Kind.DURATION
    if op == "-":
        if left in _MOMENTS:
            return Kind.DURATION if right in _MOMENTS else Kind.INSTANT
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


def _resolve(node: Node, expect: Expect, types: Types, choices: Choices) -> Node:
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
                _require_moment(date, "take the date from", types, choices),
                _resolve(time, Expect.INSTANT, types, choices),
            )

        case Assign(name=name, value=value):
            if name in SIGNATURES:
                raise DtcalcError(
                    f"{name!r} is a builtin function, so it cannot be a variable name",
                    node.start,
                    node.end,
                )
            return Assign(node.start, node.end, name, _resolve(value, expect, types, choices))

        case Negate(operand=operand):
            if (kind := _infer(operand, types)) in _MOMENTS:
                raise DtcalcError(f"cannot negate {_article(kind)}", node.start, node.end)
            return Negate(node.start, node.end, _resolve(operand, Expect.DURATION, types, choices))

        case Convert(operand=operand, zone_name=zone):
            return Convert(
                node.start, node.end, _require_moment(operand, "convert", types, choices), zone
            )

        case Attach(operand=operand, zone_name=zone):
            return Attach(
                node.start,
                node.end,
                _require_moment(operand, "attach a zone to", types, choices),
                zone,
            )

        case Binary(op=op, left=left, right=right):
            return _resolve_binary(node, op, left, right, expect, types, choices)

        case Call(name=name, args=args):
            return _resolve_call(node, name, args, types, choices)

        case _:  # pragma: no cover - every node type is covered above
            raise AssertionError(f"unhandled node {node!r}")


def _require_moment(operand: Node, verb: str, types: Types, choices: Choices) -> Node:
    """Require a date or an instant — both denote a point on the calendar."""
    kind = _infer(operand, types)
    if kind is not None and kind not in _MOMENTS:
        raise DtcalcError(
            f"can only {verb} a date or an instant, not {_article(kind)}",
            operand.start,
            operand.end,
        )
    return _resolve(operand, Expect.MOMENT, types, choices)


def _resolve_binary(
    node: Node, op: str, left: Node, right: Node, expect: Expect, types: Types, choices: Choices
) -> Node:
    if expect is Expect.EITHER and _is_ambiguous(op, left, right):
        return _resolve_ambiguous(node, op, left, right, choices)
    left_kind = _infer(left, types)
    right_kind = _infer(right, types)
    left_expect, right_expect = _operand_expectations(node, op, left_kind, right_kind)
    return Binary(
        node.start,
        node.end,
        op,
        _resolve(left, left_expect, types, choices),
        _resolve(right, right_expect, types, choices),
    )


def _is_ambiguous(op: str, left: Node, right: Node) -> bool:
    """Two bare colon literals around ``+``/``-`` where either reading is valid."""
    if op not in {"+", "-"}:
        return False
    if not (isinstance(left, ColonLit) and isinstance(right, ColonLit)):
        return False
    if left.literal.forced_duration or right.literal.forced_duration:
        return False
    try:
        _as_time_of_day(left)
    except DtcalcError:
        # Only the duration reading exists, so there is nothing to ask.
        return False
    return True


def _resolve_ambiguous(node: Node, op: str, left: Node, right: Node, choices: Choices) -> Node:
    assert isinstance(node, Binary)
    assert isinstance(left, ColonLit) and isinstance(right, ColonLit)
    choice = choices.get((node.start, node.end))
    if choice is None:
        raise AmbiguousColonError(node, left, right)
    left_expect = Expect.INSTANT if choice == "clock" else Expect.DURATION
    return Binary(
        node.start,
        node.end,
        op,
        _decide(left, left_expect),
        _decide(right, Expect.DURATION),
    )


def _operand_expectations(
    node: Node, op: str, left: Kind | None, right: Kind | None
) -> tuple[Expect, Expect]:
    """Work out what each side of a binary operator can accept."""
    if op in {"*", "/", "%"}:
        # Only durations and numbers take part; a clock reading is meaningless.
        return Expect.DURATION, Expect.DURATION

    if op == "+":
        if left in _MOMENTS and right in _MOMENTS:
            raise DtcalcError(
                "cannot add two points in time; subtract them to get the span between",
                node.start,
                node.end,
            )
        if left in _MOMENTS:
            return Expect.MOMENT, Expect.DURATION
        if right in _MOMENTS:
            return Expect.DURATION, Expect.MOMENT
        if left is None and right is None:
            # `12:15 + 12:15`: read the first as a time and the second as a
            # duration, which is the only combination that typechecks.
            return Expect.EITHER, Expect.DURATION
        return Expect.EITHER, Expect.DURATION

    if op == "-":
        if left in _MOMENTS:
            # `<instant> - 12:15` is the original request's example: a
            # duration, not "the time between noon and a quarter past".
            return Expect.MOMENT, Expect.DURATION
        if right in _MOMENTS:
            return Expect.MOMENT, Expect.MOMENT
        if left is Kind.DURATION:
            return Expect.DURATION, Expect.DURATION
        return Expect.EITHER, Expect.DURATION

    # Comparisons: both sides must be the same kind, so a known side decides.
    if left in _MOMENTS or right in _MOMENTS:
        return Expect.MOMENT, Expect.MOMENT
    if left is Kind.DURATION or right is Kind.DURATION:
        return Expect.DURATION, Expect.DURATION
    return Expect.EITHER, Expect.EITHER


def _resolve_call(
    node: Node, name: str, args: tuple[Node, ...], types: Types, choices: Choices
) -> Node:
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
        _resolve(arg, signature.expectation(position), types, choices)
        for position, arg in enumerate(args)
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
        if expect in (Expect.INSTANT, Expect.MOMENT):
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

    # Expect.INSTANT / Expect.MOMENT, and the tie-break for Expect.EITHER.
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
