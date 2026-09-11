"""Tests for the scalar value types."""

import pytest

from dtcalc.values import Boolean, Number


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (8.0, "8"),
        (0.0, "0"),
        (-3.0, "-3"),
        (0.5, "0.5"),
        (1.25, "1.25"),
        (1 / 3, "0.333333"),
        (-1 / 3, "-0.333333"),
        (1e6, "1000000"),
    ],
)
def test_number_formatting(value: float, expected: str) -> None:
    assert str(Number(value)) == expected


def test_boolean_formatting() -> None:
    assert str(Boolean(True)) == "true"
    assert str(Boolean(False)) == "false"


# --------------------------------------------------------------------------
# 3.1  the exhaustiveness guard
# --------------------------------------------------------------------------


def test_kind_has_exactly_the_expected_members() -> None:
    """A deliberate tripwire.

    Adding a value type should be a decision, not a drift. `kind_of` and
    `_describe` are exhaustive over the `Value` union via `assert_never`, so
    mypy catches an unhandled member at those sites; this catches the rest of
    the places a new kind has to be threaded through — the operator matrix,
    the resolver's expectations, the formatter.
    """
    from dtcalc.builtins import Kind

    assert {member.value for member in Kind} == {
        "date",
        "instant",
        "duration",
        "number",
        "boolean",
    }


def test_every_kind_is_produced_by_kind_of() -> None:
    """No kind exists that no value can have."""
    from datetime import UTC, datetime

    from dtcalc.builtins import Kind
    from dtcalc.date import Date
    from dtcalc.duration import Duration
    from dtcalc.instant import Instant
    from dtcalc.values import Value, kind_of

    from .support import NY

    samples: list[Value] = [
        Date(2026, 12, 24),
        Instant(datetime(2026, 12, 24, tzinfo=UTC), NY),
        Duration.build(h=1),
        Number(1.0),
        Boolean(True),
    ]
    assert {kind_of(v) for v in samples} == set(Kind)


def test_kind_of_a_date() -> None:
    from dtcalc.builtins import Kind
    from dtcalc.date import Date
    from dtcalc.values import kind_of

    assert kind_of(Date(2026, 12, 24)) is Kind.DATE
