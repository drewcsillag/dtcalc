"""Exhaustive builtin coverage across every value kind.

The companion to `test_type_matrix.py`. That file covers operators; this one
covers `functions.py`, which had twelve instant-assuming sites and would
otherwise be the one module where a missed kind could still slip through.

Kinds only. The subtleties that depend on a duration's *value* rather than its
kind — which granularities are legal, and which decide the result type — live
in `test_functions.py`, because a table keyed on kinds cannot express them.
"""

from __future__ import annotations

import pytest

from dtcalc.builtins import SIGNATURES, Kind
from dtcalc.clock import FixedClock
from dtcalc.env import Env

from .support import NY, TEST_NOW
from .test_type_matrix import SAMPLE, check

# Short aliases so the tables stay readable at a glance.
DATE, INST, DUR, NUM, BOOL = (
    Kind.DATE,
    Kind.INSTANT,
    Kind.DURATION,
    Kind.NUMBER,
    Kind.BOOLEAN,
)

# (name, argument kinds) -> result kind, or a fragment of the required error.
# A calendar granularity is used for round/trunc/ceil so the rows exercise the
# date-returning path; the exact-granularity rows are in test_functions.py.
FUNCTIONS: dict[tuple[str, tuple[Kind, ...]], Kind | str] = {}


def _add(name: str, args: tuple[Kind, ...], expected: Kind | str) -> None:
    FUNCTIONS[(name, args)] = expected


for _name in ("min", "max"):
    _add(_name, (DATE,), DATE)
    _add(_name, (INST,), INST)
    _add(_name, (DUR,), DUR)
    _add(_name, (NUM,), NUM)
    # A single argument is returned without comparing anything, so even a
    # boolean is fine; it is *comparing* booleans that refuses.
    _add(_name, (BOOL,), BOOL)
    _add(_name, (BOOL, BOOL), "dates, instants, durations or numbers")
    # Two of a kind stays that kind; mixing refuses.
    _add(_name, (DATE, DATE), DATE)
    _add(_name, (INST, INST), INST)
    _add(_name, (DUR, DUR), DUR)
    _add(_name, (NUM, NUM), NUM)
    _add(_name, (DATE, INST), "same kind")
    _add(_name, (INST, DATE), "same kind")
    _add(_name, (DATE, DUR), "same kind")
    _add(_name, (INST, DUR), "same kind")
    _add(_name, (DUR, NUM), "same kind")
    _add(_name, (NUM, BOOL), "same kind")

for _name in ("round", "trunc", "ceil"):
    # A calendar-day granularity: an instant becomes a date, a date stays one.
    _add(_name, (INST, DUR), DATE)
    _add(_name, (DATE, DUR), DATE)
    # The value sample is `3h` and the granularity `1d`: different ladders, so
    # this must refuse. The same-ladder case that yields a duration is in
    # test_functions.py, which a kind-keyed table cannot express.
    _add(_name, (DUR, DUR), "same single ladder")
    _add(_name, (NUM, DUR), "an instant, a date or a duration")
    _add(_name, (BOOL, DUR), "an instant, a date or a duration")
    # A granularity has to be a duration.
    for _kind in (DATE, INST, NUM, BOOL):
        _add(_name, (INST, _kind), "duration as its granularity")

_add("diff", (DATE, DATE), DUR)
_add("diff", (INST, INST), DUR)
_add("diff", (DATE, INST), "same kind")
_add("diff", (INST, DATE), "same kind")
for _kind in (DUR, NUM, BOOL):
    _add("diff", (_kind, _kind), "two dates or two instants")

_add("epoch", (NUM,), INST)
_add("epochms", (NUM,), INST)
for _name in ("epoch", "epochms"):
    for _kind in (DATE, INST, DUR, BOOL):
        _add(_name, (_kind,), "number")

_add("unix", (DATE,), NUM)
_add("unix", (INST,), NUM)
for _kind in (DUR, NUM, BOOL):
    _add("unix", (_kind,), "a date or an instant")

# A calendar-day granularity, so the rounding rows land on the date path.
GRANULARITY = "1d"


@pytest.fixture
def env() -> Env:
    return Env(clock=FixedClock(TEST_NOW), zone=NY)


def _call(name: str, args: tuple[Kind, ...]) -> str:
    rendered = []
    for position, kind in enumerate(args):
        if name in {"round", "trunc", "ceil"} and position == 1 and kind is Kind.DURATION:
            rendered.append(GRANULARITY)
        else:
            rendered.append(SAMPLE[kind])
    return f"{name}({', '.join(rendered)})"


@pytest.mark.parametrize(("name", "args"), sorted(FUNCTIONS, key=str))
def test_functions(env: Env, name: str, args: tuple[Kind, ...]) -> None:
    check(env, _call(name, args), FUNCTIONS[(name, args)])


def test_every_builtin_has_rows() -> None:
    assert {name for name, _ in FUNCTIONS} == set(SIGNATURES)


def test_every_kind_appears_as_a_first_argument() -> None:
    """So no kind can reach a builtin without a row saying what happens."""
    for name in SIGNATURES:
        covered = {args[0] for (n, args) in FUNCTIONS if n == name}
        assert covered == set(Kind), f"{name} is missing first-argument kinds"
