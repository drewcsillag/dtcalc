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

from calendar import monthrange
from collections.abc import Callable
from datetime import date as StdDate
from datetime import datetime, time, timedelta
from typing import Final

from dtcalc.ast import Node
from dtcalc.date import Date
from dtcalc.duration import Duration
from dtcalc.env import Env
from dtcalc.errors import DtcalcError
from dtcalc.instant import Instant
from dtcalc.values import Number, Value, kind_of

__all__ = ["call_builtin"]

_MS_PER_DAY: Final = 86_400_000
_MONTHS_PER_YEAR: Final = 12

# Day buckets are counted from a Monday, so that `trunc(x, 1w)` lands on the
# Monday of x's week rather than on whatever weekday 1970-01-01 happened to
# be (a Thursday).
_DAY_ORIGIN: Final = StdDate(1969, 12, 29)

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
                return _to_epoch(args[0], env)
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
        case Date(), Date():
            return left > right
        case Instant(), Instant():
            return left.moment > right.moment
        case Duration(), Duration():
            return left.compare(right) > 0
        case Number(), Number():
            return left.value > right.value
        case _:
            raise DtcalcError("min and max need dates, instants, durations or numbers")


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

    if granularity.bdays:
        raise DtcalcError(
            f"{name} cannot use {granularity} as a granularity: a business day has "
            f"no position within a month or a year to bucket by"
        )

    rounder = _ROUNDERS[name]
    if isinstance(value, Duration):
        # Rounding a duration is pure arithmetic within one ladder, so
        # `round(14mo, 1y)` is well defined.
        return _round_duration(value, granularity, rounder, name)

    if isinstance(value, Date):
        if granularity.millis:
            raise DtcalcError(
                f"{name} cannot use {granularity} as a granularity for a date: "
                f"a date has no time of day to round"
            )
        return _round_date(value, granularity, rounder, name)

    if isinstance(value, Instant):
        if granularity.millis:
            return _round_instant(value, granularity, rounder, env)
        # A day-or-coarser bucket names a calendar day, so the answer is a
        # date.  This is what makes `trunc(now, 1mo)` legal.
        #
        # The time of day is carried across as a fraction rather than
        # dropped: without it, `ceil(now, 1d)` would see a date already on a
        # boundary and answer today instead of tomorrow.
        wall = value.wall_clock()
        fraction = (wall - datetime.combine(wall.date(), time())) / timedelta(days=1)
        return _round_date(
            Date.from_std(wall.date()), granularity, rounder, name, fraction=fraction
        )

    raise DtcalcError(f"{name} needs an instant, a date or a duration, not a {kind_of(value)}")


def _round_date(
    value: Date,
    granularity: Duration,
    rounder: Callable[[float], int],
    name: str,
    *,
    fraction: float = 0.0,
) -> Date:
    """Bucket a calendar date by days, weeks, months or years.

    ``fraction`` is how far into the day the original value sat, which only
    an instant has.  It matters to ``ceil`` and ``round``: a value already on
    a bucket boundary must stay put, while one part-way through must not.
    """
    if granularity.months:
        if granularity.days:
            raise DtcalcError(
                f"{name} needs a granularity in one ladder; {granularity} mixes "
                f"months with days, which have no fixed ratio"
            )
        # Months counted from year zero, so `1y` lands on 1 January and `1mo`
        # on the first of the month.
        months = value.year * _MONTHS_PER_YEAR + value.month - 1
        position = months + _month_fraction(value, fraction)
        buckets = rounder(position / granularity.months)
        total = buckets * granularity.months
        return Date(total // _MONTHS_PER_YEAR, total % _MONTHS_PER_YEAR + 1, 1)

    offset = (value.to_std() - _DAY_ORIGIN).days + fraction
    buckets = rounder(offset / granularity.days)
    return Date.from_std(_DAY_ORIGIN + timedelta(days=buckets * granularity.days))


def _month_fraction(value: Date, day_fraction: float) -> float:
    """How far into its month a date sits, so ceil and round see a part-month."""
    days_in_month = monthrange(value.year, value.month)[1]
    return (value.day - 1 + day_fraction) / days_in_month


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
    match left, right:
        case Date(), Date():
            return left.diff(right)
        case Instant(), Instant():
            return left.diff(right)
        case ((Date() | Instant()), (Date() | Instant())):
            raise DtcalcError(
                "diff needs both arguments to be the same kind; mixing a date with "
                "an instant leaves it ambiguous which calendar to decompose against"
            )
        case _:
            raise DtcalcError("diff needs two dates or two instants")


def _from_epoch(value: Value, scale: int, env: Env) -> Instant:
    if not isinstance(value, Number):
        raise DtcalcError("epoch needs a number")
    try:
        moment = datetime.fromtimestamp(value.value * scale / 1000, tz=env.zone)
    except (OverflowError, OSError, ValueError) as exc:
        raise DtcalcError(f"{value} is out of range for a date and time") from exc
    return Instant(moment, env.zone)


def _to_epoch(value: Value, env: Env) -> Number:
    """Unix seconds.

    A date has no zone, so this is the one place a date acquires one
    implicitly: midnight in the working zone, which ``:tz`` reports.  Asking
    for an epoch is an explicit request for a moment, so answering beats
    refusing.
    """
    if isinstance(value, Date):
        return Number(value.at_midnight(env.zone).moment.timestamp())
    if not isinstance(value, Instant):
        raise DtcalcError(f"unix needs a date or an instant, not a {kind_of(value)}")
    return Number(value.moment.timestamp())
