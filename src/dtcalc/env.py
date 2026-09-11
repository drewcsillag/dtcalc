"""The evaluation environment: variables, display zone, clock and format."""

from __future__ import annotations

from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from dtcalc.builtins import Kind
from dtcalc.clock import Clock
from dtcalc.format import Display
from dtcalc.values import Value, kind_of

__all__ = ["Env"]


@dataclass(slots=True)
class Env:
    """Mutable state that survives between input lines."""

    clock: Clock
    zone: ZoneInfo
    fmt: str = "iso"
    clock_style: str = "24h"
    variables: dict[str, Value] = field(default_factory=dict)

    def types(self) -> dict[str, Kind]:
        """The variable types, which resolution needs to settle colon literals."""
        return {name: kind_of(value) for name, value in self.variables.items()}

    def display(self) -> Display:
        """The current display settings, including today's date.

        Today is resolved here rather than inside the formatter, so the
        formatter stays a pure function and the clock is read in one place.
        """
        return Display(
            fmt=self.fmt,
            clock=self.clock_style,
            today=self.clock.now().astimezone(self.zone).date(),
        )
