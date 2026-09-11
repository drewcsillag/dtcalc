"""The Duration value type.

A duration is a quad — ``(months, days, bdays, millis)`` — holding four
*ladders* that never convert into each other:

=============  =============  =========================================
Ladder         Units          Cascades
=============  =============  =========================================
``exact``      ms s m h       ``90m`` -> ``1h30m``; ``24h`` stays ``24h``
``caldays``    d w            ``8d`` -> ``1w1d``
``calmonths``  mo y           ``15mo`` -> ``1y3mo``
``bdays``      bd             its own ladder
=============  =============  =========================================

The separation is the whole point.  ``d`` means "same wall-clock time, next
day", which is 23, 24 or 25 hours depending on where it lands, so promoting
``24h`` to ``1d`` would silently change the meaning of an expression.

Invariant: a duration carrying business days carries no calendar days or
months, since "one business day and one calendar day" has no useful reading.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final

from dtcalc.errors import DtcalcError

__all__ = ["Duration"]

_MS_PER_SECOND: Final = 1000
_MS_PER_MINUTE: Final = 60 * _MS_PER_SECOND
_MS_PER_HOUR: Final = 60 * _MS_PER_MINUTE

# Used *only* for comparison, never for arithmetic or normalization.  See
# Duration.compare.
_NOMINAL_MS_PER_DAY: Final = 24 * _MS_PER_HOUR

EXACT: Final = "exact"
CALDAYS: Final = "caldays"
CALMONTHS: Final = "calmonths"
BDAYS: Final = "bdays"


def _whole(value: float, unit: str) -> int:
    """Coerce a calendar-unit count to an int, refusing fractions."""
    if float(value).is_integer():
        return int(value)
    raise DtcalcError(f"a calendar duration needs a whole number of {unit}, not {value:g}")


def _plural(count: int, unit: str) -> str:
    """``1 month`` rather than ``1 months``, which reads like a bug."""
    singular = {"months": "month", "days": "day", "business days": "business day"}[unit]
    return f"{count} {singular if abs(count) == 1 else unit}"


def _trunc(value: float) -> int:
    """Truncate toward zero, which is how durations lose sub-millisecond parts."""
    return int(value)


@dataclass(frozen=True, slots=True)
class Duration:
    """A signed amount of time, held as four independent ladders.

    Structural equality is exact: ``Duration.build(d=1) != Duration.build(h=24)``
    even though the language's ``==`` operator reports them as equal via
    :meth:`compare`.  The distinction is deliberate — one is "is this the same
    value", the other is "does this mean the same length of time, allowing a
    nominal 24-hour day".
    """

    months: int = 0
    days: int = 0
    bdays: int = 0
    millis: int = 0

    def __post_init__(self) -> None:
        if self.bdays and (self.months or self.days):
            raise DtcalcError("business days cannot be combined with calendar days or months")

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------

    @classmethod
    def build(
        cls,
        *,
        ms: float = 0,
        s: float = 0,
        m: float = 0,
        h: float = 0,
        d: float = 0,
        w: float = 0,
        mo: float = 0,
        y: float = 0,
        bd: float = 0,
    ) -> Duration:
        """Build a duration from unit counts.

        Exact units may be fractional (``s=1.5``); calendar units may not,
        since half a month has no meaning.
        """
        exact = ms + s * _MS_PER_SECOND + m * _MS_PER_MINUTE + h * _MS_PER_HOUR
        return cls(
            months=_whole(mo, "months") + 12 * _whole(y, "years"),
            days=_whole(d, "days") + 7 * _whole(w, "weeks"),
            bdays=_whole(bd, "business days"),
            millis=round(exact),
        )

    # ------------------------------------------------------------------
    # introspection
    # ------------------------------------------------------------------

    @property
    def ladders(self) -> frozenset[str]:
        """The names of the ladders this duration actually uses."""
        used = set()
        if self.months:
            used.add(CALMONTHS)
        if self.days:
            used.add(CALDAYS)
        if self.bdays:
            used.add(BDAYS)
        if self.millis:
            used.add(EXACT)
        return frozenset(used)

    @property
    def is_zero(self) -> bool:
        return not (self.months or self.days or self.bdays or self.millis)

    @property
    def is_exact(self) -> bool:
        """True when the duration is a plain elapsed time with no calendar part."""
        return not (self.months or self.days or self.bdays)

    def normalized(self) -> Duration:
        """Return the canonical form.

        The quad is already canonical by construction — units within a ladder
        are summed on the way in — so this is the identity.  It exists to make
        that invariant explicit and to give the property tests a handle.
        """
        return self

    # ------------------------------------------------------------------
    # arithmetic
    # ------------------------------------------------------------------

    def __add__(self, other: Duration) -> Duration:
        return Duration(
            months=self.months + other.months,
            days=self.days + other.days,
            bdays=self.bdays + other.bdays,
            millis=self.millis + other.millis,
        )

    def __sub__(self, other: Duration) -> Duration:
        return self + (-other)

    def __neg__(self) -> Duration:
        return Duration(
            months=-self.months, days=-self.days, bdays=-self.bdays, millis=-self.millis
        )

    def __mul__(self, factor: float) -> Duration:
        return Duration(
            months=_whole(self.months * factor, "months"),
            days=_whole(self.days * factor, "days"),
            bdays=_whole(self.bdays * factor, "business days"),
            millis=_trunc(self.millis * factor),
        )

    __rmul__ = __mul__

    def __truediv__(self, divisor: float) -> Duration:
        if divisor == 0:
            raise DtcalcError("cannot divide a duration by zero")
        return Duration(
            months=self._divide_calendar(self.months, divisor, "months"),
            days=self._divide_calendar(self.days, divisor, "days"),
            bdays=self._divide_calendar(self.bdays, divisor, "business days"),
            millis=_trunc(self.millis / divisor),
        )

    @staticmethod
    def _divide_calendar(value: int, divisor: float, unit: str) -> int:
        quotient = value / divisor
        if not quotient.is_integer():
            raise DtcalcError(
                f"{_plural(value, unit)} does not divide evenly by {divisor:g}; "
                f"calendar units have no fixed length, so there is no exact answer"
            )
        return int(quotient)

    def divide_by(self, other: Duration) -> float:
        """Divide by another duration, yielding a plain number."""
        if other.is_zero:
            raise DtcalcError("cannot divide by a zero duration")
        if self.is_zero:
            return 0.0
        self._require_single_shared_ladder(other, "divide")
        return self.sole_component() / other.sole_component()

    def __mod__(self, other: Duration) -> Duration:
        if other.is_zero:
            raise DtcalcError("cannot take a duration modulo zero")
        if self.is_zero:
            return self
        self._require_single_shared_ladder(other, "take the modulo of")
        left, right = self.sole_component(), other.sole_component()
        # Truncated rather than floored, so a negative left operand keeps its
        # sign: -97m % 15m is -7m.
        remainder = left - right * _trunc(left / right)
        return self._with_sole_component(int(remainder))

    # ------------------------------------------------------------------
    # comparison
    # ------------------------------------------------------------------

    def compare(self, other: Duration) -> int:
        """Three-way comparison, or an error when the answer is not knowable.

        The sign of ``self - other`` decides it whenever every non-zero ladder
        of the difference agrees in sign — which is why ``13mo > 1y`` and
        ``1mo1d > 1mo`` both work despite mixing units.

        When the ladders disagree, days and weeks fall back to a nominal 24
        hours, so ``1d < 25h`` answers ``true``.  Months and business days get
        no such fallback: a month has no nominal length worth guessing at, so
        the comparison is an error instead of a plausible-looking lie.
        """
        try:
            diff = self - other
        except DtcalcError as exc:
            raise DtcalcError(f"cannot compare {self} with {other}: {exc.message}") from exc

        signs = {
            (component > 0) - (component < 0)
            for component in (diff.months, diff.days, diff.bdays, diff.millis)
            if component
        }
        if not signs:
            return 0
        if len(signs) == 1:
            return signs.pop()

        if diff.months or diff.bdays:
            culprit = "months" if diff.months else "business days"
            raise DtcalcError(
                f"cannot compare {self} with {other}: {culprit} have no fixed length, "
                f"so there is no answer that is always right"
            )
        nominal = diff.days * _NOMINAL_MS_PER_DAY + diff.millis
        return (nominal > 0) - (nominal < 0)

    # ------------------------------------------------------------------
    # single-ladder helpers, used by / and %
    # ------------------------------------------------------------------

    def shares_a_single_ladder_with(self, other: Duration) -> bool:
        """True when both durations use exactly one ladder, and the same one."""
        return self.ladders == other.ladders and len(self.ladders) == 1

    def _require_single_shared_ladder(self, other: Duration, verb: str) -> None:
        if not self.shares_a_single_ladder_with(other):
            raise DtcalcError(
                f"can only {verb} durations in the same single ladder; {self} and {other} are not"
            )

    def sole_component(self) -> int:
        """The magnitude of the single ladder this duration uses.

        Only meaningful for a single-ladder duration; ``/``, ``%`` and
        rounding check that first.
        """
        (ladder,) = self.ladders
        return {
            CALMONTHS: self.months,
            CALDAYS: self.days,
            BDAYS: self.bdays,
            EXACT: self.millis,
        }[ladder]

    def _with_sole_component(self, value: int) -> Duration:
        (ladder,) = self.ladders
        field = {CALMONTHS: "months", CALDAYS: "days", BDAYS: "bdays", EXACT: "millis"}[ladder]
        return replace(Duration(), **{field: value})

    # ------------------------------------------------------------------
    # rendering
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        groups = [
            _render_months(abs(self.months)),
            _render_days(abs(self.days)),
            f"{abs(self.bdays)}bd" if self.bdays else "",
            _render_exact(abs(self.millis)),
        ]
        negatives = [
            self.months < 0,
            self.days < 0,
            self.bdays < 0,
            self.millis < 0,
        ]
        present = [(text, neg) for text, neg in zip(groups, negatives, strict=True) if text]
        if not present:
            return "0s"

        if len({neg for _, neg in present}) == 1:
            sign = "-" if present[0][1] else ""
            return sign + "".join(text for text, _ in present)

        # Ladders disagree in sign, as in `1d - 90m`.  Each keeps its own sign
        # and they are spaced apart, because `1d-1h30m` would read as one
        # subtraction rather than one value.
        return " ".join(("-" if neg else "") + text for text, neg in present)

    def __repr__(self) -> str:
        return f"Duration({self})"


def _render_months(months: int) -> str:
    years, rest = divmod(months, 12)
    return (f"{years}y" if years else "") + (f"{rest}mo" if rest else "")


def _render_days(days: int) -> str:
    weeks, rest = divmod(days, 7)
    return (f"{weeks}w" if weeks else "") + (f"{rest}d" if rest else "")


def _render_exact(millis: int) -> str:
    if not millis:
        return ""
    hours, rest = divmod(millis, _MS_PER_HOUR)
    minutes, rest = divmod(rest, _MS_PER_MINUTE)
    if not hours and not minutes and rest < _MS_PER_SECOND:
        return f"{rest}ms"
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if rest:
        seconds = f"{rest / _MS_PER_SECOND:.3f}".rstrip("0").rstrip(".")
        parts.append(f"{seconds}s")
    return "".join(parts)
