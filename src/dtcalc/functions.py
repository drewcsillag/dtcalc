"""Builtin function implementations.

Signatures — arity and what each position expects — live in
:mod:`dtcalc.builtins`, because resolution needs them before evaluation.

The interesting part is rounding, which has to respect the ladder model.
An *exact* granularity (``15m``, ``7h``, ``24h``) buckets elapsed time
counting up from local midnight.  A *calendar* granularity (``1d``, ``1w``)
buckets whole local dates, so ``trunc(x, 1d)`` is midnight even on the
23- and 25-hour days that daylight saving produces — which a 24-hour bucket
would get wrong.  Months, years and business days have no fixed length at
all, so they are refused as granularities rather than approximated.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date as Date
from datetime import datetime, time, timedelta
from typing import Final

from dtcalc.ast import Node
from dtcalc.duration import Duration
from dtcalc.env import Env
from dtcalc.errors import DtcalcError
from dtcalc.instant import Instant
from dtcalc.values import Number, Value, kind_of

__all__ = ["call_builtin"]

_MS_PER_DAY: Final = 86_400_000

# Day buckets are counted from a Monday, so that `trunc(x, 1w)` lands on the
# Monday of x's week rather than on whatever weekday 1970-01-01 happened to
# be (a Thursday).
_DAY_ORIGIN: Final = Date(1969, 12, 29)

_ROUNDERS: Final[dict[str, Callable[[float], int]]] = {
    "trunc": lambda q: int(q // 1),
    "ceil": lambda q: -int(-q // 1),
    "round": lambda q: int((q + 0.5) // 1),
}


def call_builtin(name: str, args: tuple[Value, ...], node: Node, env: Env) -> Value:
    """Dispatch a builtin.  Arity and argument kinds were checked at resolution."""
    try:
        match name:
            case "min":
                return _extreme(args, want_max=False)
            case "max":
                return _extreme(args, want_max=True)
            case "trunc" | "ceil" | "round":
                return _round(name, args[0], args[1], env)
            case "diff":
                return _diff(args[0], args[1])
            case "epoch":
                return _from_epoch(args[0], 1000, env)
            case "epochms":
                return _from_epoch(args[0], 1, env)
            case "unix":
                return _to_epoch(args[0])
            case _:  # pragma: no cover - resolution rejects unknown names
                raise AssertionError(f"unregistered builtin {name!r}")
    except DtcalcError as exc:
        raise DtcalcError(exc.message, node.start, node.end) from exc


# --------------------------------------------------------------------------
# min / max
# --------------------------------------------------------------------------


def _extreme(args: tuple[Value, ...], *, want_max: bool) -> Value:
    kinds = {kind_of(arg) for arg in args}
    if len(kinds) > 1:
        listed = ", ".join(sorted(kinds))
        raise DtcalcError(f"arguments must all be the same kind, but got {listed}")

    best = args[0]
    for candidate in args[1:]:
        if _greater(candidate, best) is want_max:
            best = candidate
    return best


def _greater(left: Value, right: Value) -> bool:
    match left, right:
        case Instant(), Instant():
            return left.moment > right.moment
        case Duration(), Duration():
            return left.compare(right) > 0
        case Number(), Number():
            return left.value > right.value
        case _:
            raise DtcalcError("min and max need instants, durations or numbers")


# --------------------------------------------------------------------------
# rounding
# --------------------------------------------------------------------------


def _round(name: str, value: Value, granularity: Value, env: Env) -> Value:
    if not isinstance(granularity, Duration):
        raise DtcalcError(f"{name} needs a duration as its granularity")
    if granularity.is_zero:
        raise DtcalcError(f"{name} cannot use a zero granularity")
    if _is_negative(granularity):
        raise DtcalcError(f"{name} needs a positive granularity, not {granularity}")

    rounder = _ROUNDERS[name]
    if isinstance(value, Instant):
        # Rounding an instant needs a granularity that maps onto the calendar.
        # Months, years and business days do not: there is no anchor from
        # which "the nearest month boundary" is a fixed distance away.
        if granularity.months or granularity.bdays:
            culprit = "months and years" if granularity.months else "business days"
            raise DtcalcError(
                f"{name} cannot use {granularity} as a granularity for an instant: "
                f"{culprit} have no fixed length, so there is nothing to round to"
            )
        return _round_instant(value, granularity, rounder, env)
    if isinstance(value, Duration):
        # Rounding a duration is pure arithmetic within one ladder, so
        # `round(14mo, 1y)` is perfectly well defined.
        return _round_duration(value, granularity, rounder, name)
    raise DtcalcError(f"{name} needs an instant or a duration, not a {kind_of(value)}")


def _is_negative(granularity: Duration) -> bool:
    return (
        granularity.months < 0
        or granularity.days < 0
        or granularity.bdays < 0
        or granularity.millis < 0
    )


def _round_instant(
    value: Instant, granularity: Duration, rounder: Callable[[float], int], env: Env
) -> Instant:
    if granularity.days:
        if granularity.millis:
            raise DtcalcError(
                "a granularity mixes an exact part with calendar days; use one or "
                "the other, since a day is not always 24 hours"
            )
        return _round_to_days(value, granularity.days, rounder)

    midnight = Instant.from_wall_clock(
        value.zone, datetime.combine(value.wall_clock().date(), time())
    )
    elapsed = value.elapsed_since(midnight).millis
    buckets = rounder(elapsed / granularity.millis)
    return midnight + Duration(millis=buckets * granularity.millis)


def _round_to_days(value: Instant, days: int, rounder: Callable[[float], int]) -> Instant:
    """Bucket whole local dates, which is what makes DST days come out right."""
    local = value.wall_clock()
    offset = (local.date() - _DAY_ORIGIN).days
    # A partial day counts toward the fraction, so ceil and round see it.
    fraction = (local - datetime.combine(local.date(), time())).total_seconds() * 1000
    position = offset + fraction / _MS_PER_DAY
    buckets = rounder(position / days)
    target = _DAY_ORIGIN + timedelta(days=buckets * days)
    return Instant.from_wall_clock(value.zone, datetime.combine(target, time()))


def _round_duration(
    value: Duration, granularity: Duration, rounder: Callable[[float], int], name: str
) -> Duration:
    if value.is_zero:
        return value
    if not value.shares_a_single_ladder_with(granularity):
        raise DtcalcError(
            f"{name} needs the value and the granularity in the same single ladder; "
            f"{value} and {granularity} are not"
        )
    unit = granularity.sole_component()
    current = value.sole_component()
    # Round the magnitude and restore the sign, so -97m rounds to -1h30m
    # rather than to -1h45m.
    sign = -1 if current < 0 else 1
    buckets = rounder(abs(current) / unit)
    return granularity * float(sign * buckets)


# --------------------------------------------------------------------------
# differences and epoch conversion
# --------------------------------------------------------------------------


def _diff(left: Value, right: Value) -> Duration:
    if not isinstance(left, Instant) or not isinstance(right, Instant):
        raise DtcalcError("diff needs two instants")
    return left.diff(right)


def _from_epoch(value: Value, scale: int, env: Env) -> Instant:
    if not isinstance(value, Number):
        raise DtcalcError("epoch needs a number")
    try:
        moment = datetime.fromtimestamp(value.value * scale / 1000, tz=env.zone)
    except (OverflowError, OSError, ValueError) as exc:
        raise DtcalcError(f"{value} is out of range for a date and time") from exc
    return Instant(moment, env.zone)


def _to_epoch(value: Value) -> Number:
    if not isinstance(value, Instant):
        raise DtcalcError("unix needs an instant")
    return Number(value.moment.timestamp())
