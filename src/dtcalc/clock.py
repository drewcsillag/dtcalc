"""The clock, as an injected dependency.

Nothing in dtcalc calls :func:`datetime.datetime.now` directly.  ``now`` is
read from a :class:`Clock`, which means every test that touches it can freeze
time, and the CLI can honour ``DTCALC_NOW``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

__all__ = ["Clock", "FixedClock", "SystemClock"]


class Clock(Protocol):
    """Source of the current instant, always timezone-aware and in UTC."""

    def now(self) -> datetime: ...


class SystemClock:
    """The real clock, read to the second.

    Sub-second precision is dropped deliberately.  This is a tool for
    scheduling arithmetic, and a stray ``.379051`` on the end of every result
    is noise rather than information.  Sub-second values are still available
    where they are meant: written literals such as ``12:15:13.5`` and
    durations such as ``250ms``.
    """

    def now(self) -> datetime:
        return datetime.now(UTC).replace(microsecond=0)


class FixedClock:
    """A clock frozen at a single instant, for tests and ``DTCALC_NOW``."""

    def __init__(self, instant: datetime) -> None:
        if instant.tzinfo is None:
            raise ValueError("a fixed clock needs an aware datetime")
        self._instant = instant.astimezone(UTC)

    def now(self) -> datetime:
        return self._instant
