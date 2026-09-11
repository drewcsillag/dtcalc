"""Builtin function signatures.

The table lives apart from the implementations because resolution needs it
first: to decide what ``round(12:15, 15m)`` means, the resolver has to know
that ``round`` takes a value and then an exact granularity.  The
implementations in :mod:`dtcalc.functions` are checked against the same table,
so the two cannot drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

__all__ = ["SIGNATURES", "Expect", "Kind", "Signature"]


class Kind(StrEnum):
    """The type of a value, as far as static reasoning can tell."""

    DATE = "date"
    INSTANT = "instant"
    DURATION = "duration"
    NUMBER = "number"
    BOOLEAN = "boolean"


class Expect(StrEnum):
    """What a position wants, which is how a colon literal gets decided."""

    INSTANT = "instant"
    # A date or an instant: what `in`, `@ zone` and the rounding functions
    # accept, since both denote a point on the calendar.
    MOMENT = "moment"
    DURATION = "duration"
    NUMBER = "number"
    EITHER = "either"


@dataclass(frozen=True, slots=True)
class Signature:
    """Arity and per-position expectations for a builtin.

    ``expects`` is positional; its final entry repeats for a variadic
    function.  ``returns`` of ``None`` means "the same kind as the first
    argument", which is what ``min``, ``max``, ``round``, ``trunc`` and
    ``ceil`` all do.
    """

    min_args: int
    max_args: int | None
    expects: tuple[Expect, ...]
    returns: Kind | None

    def expectation(self, position: int) -> Expect:
        if position < len(self.expects):
            return self.expects[position]
        return self.expects[-1]


SIGNATURES: Final[dict[str, Signature]] = {
    "min": Signature(1, None, (Expect.EITHER,), None),
    "max": Signature(1, None, (Expect.EITHER,), None),
    "round": Signature(2, 2, (Expect.EITHER, Expect.DURATION), None),
    "trunc": Signature(2, 2, (Expect.EITHER, Expect.DURATION), None),
    "ceil": Signature(2, 2, (Expect.EITHER, Expect.DURATION), None),
    "diff": Signature(2, 2, (Expect.MOMENT, Expect.MOMENT), Kind.DURATION),
    "epoch": Signature(1, 1, (Expect.NUMBER,), Kind.INSTANT),
    "epochms": Signature(1, 1, (Expect.NUMBER,), Kind.INSTANT),
    "unix": Signature(1, 1, (Expect.MOMENT,), Kind.NUMBER),
}
