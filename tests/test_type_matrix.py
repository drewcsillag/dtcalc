"""Exhaustive operator and function coverage across every value kind.

The risk this file exists for: adding a fifth kind means every site that
dispatches on a value's type has to learn about it, and a missed site degrades
*silently* rather than crashing. Picking examples cannot show that nothing was
missed; a table can.

Each row names an operator or function, the kinds of its operands, and either
the kind of the result or a fragment of the error it must raise. A combination
absent from the table fails `test_the_matrix_is_exhaustive`, so a sixth kind
forces the table to grow rather than quietly leaving holes.
"""

from __future__ import annotations

import itertools

import pytest

from dtcalc.builtins import SIGNATURES, Kind
from dtcalc.clock import FixedClock
from dtcalc.env import Env
from dtcalc.errors import DtcalcError
from dtcalc.evaluator import evaluate_line
from dtcalc.values import kind_of

from .support import NY, TEST_NOW

# One expression per kind, so a row can be assembled mechanically.
#
# The duration sample is deliberately **exact**. A table keyed on kinds cannot
# distinguish `3h` from `1d` — both are Kind.DURATION — so it cannot express
# the promotion rule, which turns on a duration's *value*. That belongs in
# test_evaluator.py; here the exact sample means every `date + duration` row
# lands on the promoting path.
SAMPLE: dict[Kind, str] = {
    Kind.DATE: "2026-12-24",
    Kind.INSTANT: "2026-12-24T09:00",
    Kind.DURATION: "3h",
    Kind.NUMBER: "2",
    Kind.BOOLEAN: "(1h < 2h)",
}

BINARY_OPS = ("+", "-", "*", "/", "%")
COMPARISONS = ("<", "<=", ">", ">=", "==", "!=")

# Short aliases so the tables stay readable at a glance.
DATE, INST, DUR, NUM, BOOL = (
    Kind.DATE,
    Kind.INSTANT,
    Kind.DURATION,
    Kind.NUMBER,
    Kind.BOOLEAN,
)

# (op, left, right) -> result kind, or a fragment of the required error.
ARITHMETIC: dict[tuple[str, Kind, Kind], Kind | str] = {
    # Addition: a point in time plus a span, in either order.
    # The duration sample is exact, so these promote; the calendar-duration
    # case that keeps a date a date is covered in test_evaluator.py.
    ("+", DATE, DUR): INST,
    ("+", DUR, DATE): INST,
    ("+", INST, DUR): INST,
    ("+", DUR, INST): INST,
    ("+", DUR, DUR): DUR,
    ("+", NUM, NUM): NUM,
    ("+", DATE, DATE): "cannot add two points in time",
    ("+", DATE, INST): "cannot add two points in time",
    ("+", INST, DATE): "cannot add two points in time",
    ("+", INST, INST): "cannot add two points in time",
    ("+", DATE, NUM): "cannot add",
    ("+", NUM, DATE): "cannot add",
    ("+", INST, NUM): "cannot add",
    ("+", NUM, INST): "cannot add",
    ("+", DUR, NUM): "cannot add",
    ("+", NUM, DUR): "cannot add",
    # Subtraction: the feature lives on the (date, date) row.
    ("-", DATE, DATE): DUR,
    ("-", INST, INST): DUR,
    ("-", DATE, INST): DUR,
    ("-", INST, DATE): DUR,
    ("-", DATE, DUR): INST,
    ("-", INST, DUR): INST,
    ("-", DUR, DUR): DUR,
    ("-", NUM, NUM): NUM,
    ("-", DUR, DATE): "cannot subtract",
    ("-", DUR, INST): "cannot subtract",
    ("-", DATE, NUM): "cannot subtract",
    ("-", NUM, DATE): "cannot subtract",
    ("-", INST, NUM): "cannot subtract",
    ("-", NUM, INST): "cannot subtract",
    ("-", DUR, NUM): "cannot subtract",
    ("-", NUM, DUR): "cannot subtract",
    # Scaling: only spans and numbers.
    ("*", DUR, NUM): DUR,
    ("*", NUM, DUR): DUR,
    ("*", NUM, NUM): NUM,
    ("*", DATE, NUM): "cannot multiply",
    ("*", NUM, DATE): "cannot multiply",
    ("*", INST, NUM): "cannot multiply",
    ("*", NUM, INST): "cannot multiply",
    ("*", DATE, DATE): "cannot multiply",
    ("*", DATE, INST): "cannot multiply",
    ("*", INST, DATE): "cannot multiply",
    ("*", INST, INST): "cannot multiply",
    ("*", DATE, DUR): "cannot multiply",
    ("*", DUR, DATE): "cannot multiply",
    ("*", INST, DUR): "cannot multiply",
    ("*", DUR, INST): "cannot multiply",
    ("*", DUR, DUR): "cannot multiply",
    ("/", DUR, NUM): DUR,
    ("/", DUR, DUR): NUM,
    ("/", NUM, NUM): NUM,
    ("/", DATE, NUM): "cannot divide",
    ("/", NUM, DATE): "cannot divide",
    ("/", INST, NUM): "cannot divide",
    ("/", NUM, INST): "cannot divide",
    ("/", DATE, DATE): "cannot divide",
    ("/", DATE, INST): "cannot divide",
    ("/", INST, DATE): "cannot divide",
    ("/", INST, INST): "cannot divide",
    ("/", DATE, DUR): "cannot divide",
    ("/", DUR, DATE): "cannot divide",
    ("/", INST, DUR): "cannot divide",
    ("/", DUR, INST): "cannot divide",
    ("/", NUM, DUR): "cannot divide",
    ("%", DUR, DUR): DUR,
    ("%", DATE, DATE): "cannot take",
    ("%", INST, INST): "cannot take",
    ("%", NUM, NUM): "cannot take",
    ("%", DATE, INST): "cannot take",
    ("%", INST, DATE): "cannot take",
    ("%", DATE, DUR): "cannot take",
    ("%", DUR, DATE): "cannot take",
    ("%", INST, DUR): "cannot take",
    ("%", DUR, INST): "cannot take",
    ("%", DATE, NUM): "cannot take",
    ("%", NUM, DATE): "cannot take",
    ("%", INST, NUM): "cannot take",
    ("%", NUM, INST): "cannot take",
    ("%", DUR, NUM): "cannot take",
    ("%", NUM, DUR): "cannot take",
}

# Booleans take part in nothing arithmetic, so those rows are generated.
for _op in BINARY_OPS:
    for _other in (DATE, INST, DUR, NUM, BOOL):
        ARITHMETIC.setdefault((_op, BOOL, _other), "cannot")
        ARITHMETIC.setdefault((_op, _other, BOOL), "cannot")

# Comparison: same-kind compares, cross-kind refuses, except that a date and
# an instant are both points in time and compare by promoting the date.
COMPARISON: dict[tuple[Kind, Kind], Kind | str] = {
    (DATE, DATE): BOOL,
    (INST, INST): BOOL,
    (DATE, INST): BOOL,
    (INST, DATE): BOOL,
    (DUR, DUR): BOOL,
    (NUM, NUM): BOOL,
    (BOOL, BOOL): BOOL,
    (DATE, DUR): "cannot compare",
    (DUR, DATE): "cannot compare",
    (INST, DUR): "cannot compare",
    (DUR, INST): "cannot compare",
    (DATE, NUM): "cannot compare",
    (NUM, DATE): "cannot compare",
    (INST, NUM): "cannot compare",
    (NUM, INST): "cannot compare",
    (DUR, NUM): "cannot compare",
    (NUM, DUR): "cannot compare",
    (DATE, BOOL): "cannot compare",
    (BOOL, DATE): "cannot compare",
    (INST, BOOL): "cannot compare",
    (BOOL, INST): "cannot compare",
    (DUR, BOOL): "cannot compare",
    (BOOL, DUR): "cannot compare",
    (NUM, BOOL): "cannot compare",
    (BOOL, NUM): "cannot compare",
}

# Unary minus, which the matrix originally omitted.
UNARY: dict[Kind, Kind | str] = {
    DUR: DUR,
    NUM: NUM,
    DATE: "cannot negate a date",
    INST: "cannot negate an instant",
    BOOL: "cannot negate",
}

# Zone naming: a date or an instant accepts it, nothing else does.
ZONE: dict[Kind, Kind | str] = {
    DATE: INST,
    INST: INST,
    DUR: "a date or an instant",
    NUM: "a date or an instant",
    BOOL: "a date or an instant",
}


@pytest.fixture
def env() -> Env:
    return Env(clock=FixedClock(TEST_NOW), zone=NY)


def check(env: Env, source: str, expected: Kind | str) -> None:
    """Evaluate and assert the result kind, or the required error fragment."""
    if isinstance(expected, Kind):
        assert kind_of(evaluate_line(source, env)) is expected, source
        return
    with pytest.raises(DtcalcError, match=expected):
        evaluate_line(source, env)


@pytest.mark.parametrize(("op", "left", "right"), sorted(ARITHMETIC, key=str))
def test_arithmetic(env: Env, op: str, left: Kind, right: Kind) -> None:
    check(env, f"{SAMPLE[left]} {op} {SAMPLE[right]}", ARITHMETIC[(op, left, right)])


@pytest.mark.parametrize(("left", "right"), sorted(COMPARISON, key=str))
@pytest.mark.parametrize("op", COMPARISONS)
def test_comparison(env: Env, op: str, left: Kind, right: Kind) -> None:
    check(env, f"{SAMPLE[left]} {op} {SAMPLE[right]}", COMPARISON[(left, right)])


@pytest.mark.parametrize("kind", sorted(UNARY, key=str))
def test_unary_minus(env: Env, kind: Kind) -> None:
    check(env, f"-{SAMPLE[kind]}", UNARY[kind])


@pytest.mark.parametrize("kind", sorted(ZONE, key=str))
@pytest.mark.parametrize("operator", ["in", "@"])
def test_zone_naming(env: Env, kind: Kind, operator: str) -> None:
    check(env, f"{SAMPLE[kind]} {operator} Tokyo", ZONE[kind])


# --------------------------------------------------------------------------
# the table must cover everything
# --------------------------------------------------------------------------


def test_the_matrix_is_exhaustive() -> None:
    """Every operator against every ordered pair of kinds has a row.

    This is the assertion that makes the file worth its length: a sixth kind
    cannot be added without the table growing to meet it.
    """
    missing = [
        (op, left, right)
        for op in BINARY_OPS
        for left, right in itertools.product(Kind, repeat=2)
        if (op, left, right) not in ARITHMETIC
    ]
    assert not missing, f"arithmetic rows missing: {missing}"

    missing_pairs = [pair for pair in itertools.product(Kind, repeat=2) if pair not in COMPARISON]
    assert not missing_pairs, f"comparison rows missing: {missing_pairs}"

    assert set(UNARY) == set(Kind)
    assert set(ZONE) == set(Kind)
    assert set(SAMPLE) == set(Kind)


def test_every_sample_really_has_the_kind_it_claims(env: Env) -> None:
    """A wrong sample would make the whole matrix test the wrong thing."""
    for kind, source in SAMPLE.items():
        assert kind_of(evaluate_line(source, env)) is kind, source


def test_every_builtin_appears_in_the_function_matrix() -> None:
    from .test_function_matrix import FUNCTIONS

    assert {name for name, _ in FUNCTIONS} == set(SIGNATURES)
