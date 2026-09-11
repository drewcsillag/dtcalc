"""Tests for the injected clock."""

from datetime import UTC, datetime

import pytest

from dtcalc.clock import FixedClock, SystemClock

from .support import NY, TEST_NOW


def test_fixed_clock_returns_the_same_instant_every_time(frozen_clock: FixedClock) -> None:
    assert frozen_clock.now() == frozen_clock.now() == TEST_NOW


def test_fixed_clock_normalises_to_utc() -> None:
    clock = FixedClock(datetime(2026, 5, 23, 12, 15, 13, tzinfo=NY))
    assert clock.now().tzinfo is UTC
    assert clock.now() == datetime(2026, 5, 23, 16, 15, 13, tzinfo=UTC)


def test_fixed_clock_rejects_a_naive_datetime() -> None:
    with pytest.raises(ValueError, match="aware"):
        FixedClock(datetime(2026, 5, 23, 12, 15, 13))


def test_system_clock_is_aware_and_utc() -> None:
    assert SystemClock().now().tzinfo is UTC


def test_the_system_clock_drops_sub_second_noise() -> None:
    assert SystemClock().now().microsecond == 0


def test_a_fixed_clock_keeps_sub_second_precision() -> None:
    """Only the real clock truncates; explicit values are honoured exactly."""
    precise = datetime(2026, 5, 23, 12, 15, 13, 500_000, tzinfo=NY)
    assert FixedClock(precise).now().microsecond == 500_000
