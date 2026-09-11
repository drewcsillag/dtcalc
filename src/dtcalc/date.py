"""The Date value type: a calendar day, with no time and no zone.

The absence of a zone is the whole point. Subtracting two instants measures
elapsed time, so it has to answer in hours; subtracting two dates counts days
off a calendar, where clock changes simply do not apply. That is why
``2027-01-03 - 2026-12-24`` is ten days rather than 240 hours.

A date stays a date under calendar arithmetic and becomes an
:class:`~dtcalc.instant.Instant` the moment anything names a time — an exact
duration, a clock reading, or a zone. :meth:`Date.promotes` is that rule, and
it reads straight off the ladders a duration already reports.
"""

from __future__ import annotations

import calendar
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date as StdDate
from datetime import datetime, time, timedelta
from typing import Final
from zoneinfo import ZoneInfo

from dtcalc.duration import Duration
from dtcalc.errors import DtcalcError
from dtcalc.instant import Instant

__all__ = ["Date"]

_SATURDAY: Final = 5
_MONTHS_PER_YEAR: Final = 12
_MIN_YEAR: Final = 1
_MAX_YEAR: Final = 9999


@dataclass(frozen=True, slots=True, order=True)
class Date:
    """A calendar day. Ordered, hashable, and deliberately zoneless."""

    year: int
    month: int
    day: int

    def __post_init__(self) -> None:
        try:
            StdDate(self.year, self.month, self.day)
        except ValueError as exc:
            raise DtcalcError(f"{self.year}-{self.month}-{self.day} is not a real date") from exc

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------

    @classmethod
    def from_iso(cls, text: str) -> Date:
        try:
            parsed = StdDate.fromisoformat(text)
        except ValueError as exc:
            raise DtcalcError(f"{text!r} is not a date in YYYY-MM-DD form") from exc
        return cls.from_std(parsed)

    @classmethod
    def from_std(cls, value: StdDate) -> Date:
        return cls(value.year, value.month, value.day)

    def to_std(self) -> StdDate:
        return StdDate(self.year, self.month, self.day)

    def weekday(self) -> int:
        """Monday is 0, matching the standard library and the lexer."""
        return self.to_std().weekday()

    # ------------------------------------------------------------------
    # promotion
    # ------------------------------------------------------------------

    @staticmethod
    def promotes(duration: Duration) -> bool:
        """True when adding ``duration`` to a date yields an instant.

        A date survives calendar arithmetic — days, weeks, months, years,
        business days — and gives way to an instant as soon as an *exact*
        amount of time is involved, because that names a moment within the
        day.  A zero exact part names nothing, so ``+ 0s`` stays a date.
        """
        return bool(duration.millis)

    def at_midnight(self, zone: ZoneInfo) -> Instant:
        """This date at 00:00 in ``zone`` — how a date becomes a moment."""
        return self.at_time(zone, 0, 0, 0, 0)

    def at_time(
        self, zone: ZoneInfo, hour: int, minute: int, second: int, microsecond: int
    ) -> Instant:
        """This date at a named clock reading in ``zone``."""
        wall = datetime.combine(self.to_std(), time(hour, minute, second, microsecond))
        return Instant.from_wall_clock(zone, wall, strict=False)

    # ------------------------------------------------------------------
    # arithmetic
    # ------------------------------------------------------------------

    def __add__(self, duration: Duration) -> Date:
        """Apply the calendar parts of ``duration``.

        The caller is responsible for having checked :meth:`promotes` first;
        any exact part is ignored here rather than silently rounded, because
        by construction there is none.
        """
        try:
            value = self.to_std()
            if duration.months:
                value = _add_months(value, duration.months)
            if duration.days:
                value = value + timedelta(days=duration.days)
            if duration.bdays:
                value = _add_business_days(value, duration.bdays)
        except (OverflowError, ValueError, OSError) as exc:
            raise DtcalcError(f"result is out of range: {exc}") from exc
        return Date.from_std(value)

    def __sub__(self, duration: Duration) -> Date:
        return self + (-duration)

    def days_since(self, other: Date) -> Duration:
        """The span from ``other`` to this date, in **calendar days**.

        Contrast :meth:`~dtcalc.instant.Instant.elapsed_since`, which measures
        elapsed time and must answer in hours.  Nothing here can be affected
        by a daylight-saving transition, because a date has no time of day for
        one to shift.
        """
        return Duration(days=(self.to_std() - other.to_std()).days)

    def diff(self, other: Date) -> Duration:
        """The calendar duration ``x`` for which ``self + x == other``.

        Decomposed months-first, so a span reads the way a person would say
        it: ``1mo3d`` rather than ``34d``.  Plain subtraction answers the
        other question.
        """
        if other < self:
            return -other.diff(self)
        months = _greedy(lambda n: self + Duration(months=n), other)
        after_months = self + Duration(months=months)
        days = (other.to_std() - after_months.to_std()).days
        return Duration(months=months, days=days)

    # ------------------------------------------------------------------
    # rendering
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"

    def __repr__(self) -> str:
        return f"Date({self})"


def _add_months(value: StdDate, months: int) -> StdDate:
    """Shift by whole months, clamping the day of month.

    31 January plus one month is 28 February, the same rule instants use.
    """
    zero_based = value.month - 1 + months
    year = value.year + zero_based // _MONTHS_PER_YEAR
    month = zero_based % _MONTHS_PER_YEAR + 1
    if not _MIN_YEAR <= year <= _MAX_YEAR:
        raise OverflowError(f"year {year} is outside the supported range")
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _add_business_days(value: StdDate, bdays: int) -> StdDate:
    """Step whole days, skipping weekends, as instants do."""
    step = 1 if bdays > 0 else -1
    remaining = abs(bdays)
    current = value
    while remaining:
        current += timedelta(days=step)
        while current.weekday() >= _SATURDAY:
            current += timedelta(days=step)
        remaining -= 1
    return current


def _greedy(build: Callable[[int], Date], target: Date) -> int:
    """Largest ``n >= 0`` with ``build(n) <= target``, doubling then bisecting."""

    def fits(n: int) -> bool:
        try:
            return build(n) <= target
        except DtcalcError:
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
