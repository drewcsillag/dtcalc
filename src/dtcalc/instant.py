"""The Instant value type: a point in time, plus the zone it is displayed in.

Two kinds of arithmetic live here and they must not be confused:

*exact*
    Hours, minutes, seconds and milliseconds are elapsed time.  They are
    applied in UTC and the result converted back, because adding a
    ``timedelta`` to an aware ``datetime`` in Python moves the *wall clock*
    rather than the instant — over the end of daylight saving, ``+24h`` that
    way advances 25 real hours.

*calendar*
    Months, days, weeks and business days move wall-clock fields and then
    re-localize, so ``+1d`` means "same time tomorrow" whatever that costs in
    elapsed hours.

A duration applies its calendar parts first and its exact parts second, which
is the same order PostgreSQL uses and the only order where ``+1d2h`` reads the
way it looks.
"""

from __future__ import annotations

import calendar
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final
from zoneinfo import ZoneInfo

from dtcalc.duration import Duration
from dtcalc.errors import DtcalcError

__all__ = ["Instant"]

_SATURDAY: Final = 5
_MS = 1000

_NONEXISTENT_NOTE = (
    "note: {wall} does not exist in {zone} (clocks skip forward), so it was moved forward"
)
_AMBIGUOUS_NOTE = (
    "note: {wall} happens twice in {zone} (clocks fall back); the earlier one was used"
)


def _is_weekend(day: datetime) -> bool:
    return day.weekday() >= _SATURDAY


@dataclass(frozen=True, slots=True)
class Instant:
    """A point in time (``moment``, always UTC) and its display zone.

    ``note`` carries a DST advisory produced by arithmetic.  It is excluded
    from equality: two instants that denote the same moment are the same
    instant regardless of how they got there.
    """

    moment: datetime
    zone: ZoneInfo
    note: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if self.moment.tzinfo is None:
            raise DtcalcError("an instant needs a timezone")

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------

    @classmethod
    def from_wall_clock(cls, zone: ZoneInfo, naive: datetime, *, strict: bool = False) -> Instant:
        """Interpret naive wall-clock fields as a time in ``zone``.

        ``strict`` distinguishes a value the user typed from one arithmetic
        produced.  A literal naming a time that does not exist, or one that
        happens twice, is a mistake worth reporting; the same situation
        reached by adding a day to a valid instant is not the user's doing, so
        it resolves with an advisory note instead.
        """
        if naive.tzinfo is not None:
            naive = naive.replace(tzinfo=None)

        earlier = naive.replace(tzinfo=zone, fold=0)
        later = naive.replace(tzinfo=zone, fold=1)

        # Nonexistent: converting out and back does not return what went in.
        round_tripped = earlier.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
        if round_tripped != naive:
            if strict:
                raise DtcalcError(
                    f"{naive.isoformat()} does not exist in {zone}: the clocks skip forward over it"
                )
            after, before = later.utcoffset(), earlier.utcoffset()
            assert after is not None and before is not None  # aware by construction
            # The gap is how much the clocks jumped; step over it, not back.
            shifted = naive + (after - before)
            return cls(
                shifted.replace(tzinfo=zone).astimezone(UTC),
                zone,
                _NONEXISTENT_NOTE.format(wall=naive.isoformat(), zone=zone),
            )

        # Ambiguous: the two folds disagree about the offset.
        if earlier.utcoffset() != later.utcoffset():
            if strict:
                raise DtcalcError(
                    f"{naive.isoformat()} happens twice in {zone}: the clocks fall back over it"
                )
            return cls(
                earlier.astimezone(UTC),
                zone,
                _AMBIGUOUS_NOTE.format(wall=naive.isoformat(), zone=zone),
            )

        return cls(earlier.astimezone(UTC), zone)

    # ------------------------------------------------------------------
    # zones
    # ------------------------------------------------------------------

    def wall_clock(self) -> datetime:
        """The naive wall-clock reading in the display zone."""
        return self.moment.astimezone(self.zone).replace(tzinfo=None)

    def aware(self) -> datetime:
        """The instant as an aware datetime in the display zone."""
        return self.moment.astimezone(self.zone)

    def convert_to(self, zone: ZoneInfo) -> Instant:
        """Same instant, rendered in another zone — the ``in`` operator."""
        return Instant(self.moment, zone, self.note)

    def attach(self, zone: ZoneInfo) -> Instant:
        """Reinterpret this instant's wall clock as being in ``zone``.

        This is the ``@`` operator: ``12:13 @ SanFrancisco`` takes the reading
        12:13 and says it was a San Francisco clock showing it.  The *display*
        zone is left alone, which is the whole point — you attach a foreign
        zone in order to see the result in your own.
        """
        reinterpreted = Instant.from_wall_clock(zone, self.wall_clock())
        return Instant(reinterpreted.moment, self.zone, reinterpreted.note)

    # ------------------------------------------------------------------
    # arithmetic
    # ------------------------------------------------------------------

    def __add__(self, duration: Duration) -> Instant:
        try:
            result = self._add_calendar(duration)
            return result._add_exact(duration.millis)
        except (OverflowError, ValueError, OSError) as exc:
            raise DtcalcError(f"result is out of range: {exc}") from exc

    def __sub__(self, duration: Duration) -> Instant:
        return self + (-duration)

    def elapsed_since(self, other: Instant) -> Duration:
        """The *exact* duration from ``other`` to ``self``.

        Elapsed time, not a calendar span: a week apart is ``168h``, and a day
        that crossed the end of daylight saving is ``25h``.  Use :meth:`diff`
        when you want the calendar reading.
        """
        elapsed = self.moment - other.moment
        return Duration(millis=round(elapsed.total_seconds() * _MS))

    def _add_calendar(self, duration: Duration) -> Instant:
        if not (duration.months or duration.days or duration.bdays):
            return self

        wall = self.wall_clock()
        if duration.months:
            wall = _add_months(wall, duration.months)
        if duration.days:
            wall = wall + timedelta(days=duration.days)
        if duration.bdays:
            wall = _add_business_days(wall, duration.bdays)
        return Instant.from_wall_clock(self.zone, wall)

    def _add_exact(self, millis: int) -> Instant:
        if not millis:
            return self
        moved = self.moment + timedelta(milliseconds=millis)
        return Instant(moved, self.zone, self.note)

    # ------------------------------------------------------------------
    # differences
    # ------------------------------------------------------------------

    def diff(self, other: Instant) -> Duration:
        """The calendar duration ``d`` for which ``self + d == other``.

        Decomposed largest-unit-first against the endpoints, so a day that
        happens to be 25 hours long still reads as ``1d``.  Contrast plain
        subtraction, which measures elapsed time and would say ``25h``.
        """
        if other.moment < self.moment:
            return -other.diff(self)

        months = _greedy(lambda n: self + Duration(months=n), other)
        after_months = self + Duration(months=months)
        days = _greedy(lambda n: after_months + Duration(days=n), other)
        after_days = after_months + Duration(days=days)
        remainder = other.elapsed_since(after_days)
        return Duration(months=months, days=days) + remainder

    # ------------------------------------------------------------------
    # rendering
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        aware = self.aware()
        stamp = aware.isoformat()
        if aware.microsecond:
            # isoformat pads microseconds to six digits; trim the noise.
            head, _, tail = stamp.partition(".")
            fraction = tail[:6].rstrip("0")
            offset = tail[6:]
            stamp = f"{head}.{fraction}{offset}"
        return f"{stamp}  {self.zone}"

    def __repr__(self) -> str:
        return f"Instant({self})"


def _add_months(wall: datetime, months: int) -> datetime:
    """Shift by whole months, clamping the day of month.

    31 January plus one month is 28 February, because the alternative — 3
    March — would mean ``+1mo`` sometimes skipped a month entirely.
    """
    zero_based = wall.month - 1 + months
    year = wall.year + zero_based // 12
    month = zero_based % 12 + 1
    if not 1 <= year <= 9999:
        raise OverflowError(f"year {year} is outside the supported range")
    day = min(wall.day, calendar.monthrange(year, month)[1])
    return wall.replace(year=year, month=month, day=day)


def _add_business_days(wall: datetime, bdays: int) -> datetime:
    """Step whole days, skipping weekends, so each step lands on Mon-Fri.

    From a Saturday, ``+1bd`` is Monday: the first step moves onto a business
    day rather than past one.
    """
    step = 1 if bdays > 0 else -1
    remaining = abs(bdays)
    current = wall
    while remaining:
        current += timedelta(days=step)
        while _is_weekend(current):
            current += timedelta(days=step)
        remaining -= 1
    return current


def _greedy(build: Callable[[int], Instant], target: Instant) -> int:
    """Largest ``n >= 0`` with ``build(n) <= target``, by doubling then bisecting.

    Doubling rather than stepping so that a decade-wide difference costs a
    few dozen probes instead of a few thousand.
    """

    def fits(n: int) -> bool:
        try:
            return build(n).moment <= target.moment
        except DtcalcError:
            # Ran off the end of the datetime range, so n is too large.
            return False

    if not fits(1):
        return 0
    low, high = 1, 2
    while fits(high):
        low, high = high, high * 2
    while high - low > 1:
        mid = (low + high) // 2
        if fits(mid):
            low = mid
        else:
            high = mid
    return low
