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
