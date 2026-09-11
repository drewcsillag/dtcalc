"""The value types the language computes with.

``Number`` and ``Boolean`` are thin wrappers rather than bare ``float`` and
``bool``.  The wrapping earns its keep twice: it keeps the value union
explicit for the evaluator's type checks, and it gives each type one place to
own its own rendering — which matters because ``bool`` is a subclass of
``int`` in Python and would otherwise be indistinguishable from a number.
"""

from __future__ import annotations

from dataclasses import dataclass

from dtcalc.builtins import Kind
from dtcalc.duration import Duration
from dtcalc.instant import Instant

__all__ = ["Boolean", "Number", "Value", "format_number", "kind_of"]

# Enough precision to be useful, few enough digits that float noise from
# division does not leak into the output.
_SIGNIFICANT_DECIMALS = 6


def format_number(value: float) -> str:
    """Render a number: integral values as integers, otherwise trimmed decimals."""
    if value == int(value):
        return str(int(value))
    return f"{value:.{_SIGNIFICANT_DECIMALS}f}".rstrip("0").rstrip(".")


@dataclass(frozen=True, slots=True)
class Number:
    """A dimensionless number, as produced by dividing two durations."""

    value: float

    def __str__(self) -> str:
        return format_number(self.value)


@dataclass(frozen=True, slots=True)
class Boolean:
    """The result of a comparison."""

    value: bool

    def __str__(self) -> str:
        return "true" if self.value else "false"


type Value = Instant | Duration | Number | Boolean


def kind_of(value: Value) -> Kind:
    """The static kind of a runtime value."""
    match value:
        case Instant():
            return Kind.INSTANT
        case Duration():
            return Kind.DURATION
        case Number():
            return Kind.NUMBER
        case Boolean():
            return Kind.BOOLEAN
