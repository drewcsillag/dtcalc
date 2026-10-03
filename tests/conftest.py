"""Shared fixtures.

Built before any of the test modules that use them, so the whole suite has one
determinism story: time comes from a frozen clock and the display zone is
forced, so no test depends on the machine's wall clock or local timezone.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

import pytest
from hypothesis import settings

from dtcalc.clock import FixedClock

from .support import NY, TEST_NOW

# The properties check values, not speed. Hypothesis's default 200ms deadline
# fails on a loaded machine (the first call loads tz data) and then reports the
# test as flaky, which says nothing about dtcalc.
settings.register_profile("dtcalc", deadline=None)
settings.load_profile("dtcalc")


@pytest.fixture
def frozen_clock() -> FixedClock:
    """A clock stopped at :data:`tests.support.TEST_NOW`."""
    return FixedClock(TEST_NOW)


@pytest.fixture
def fixed_zone() -> ZoneInfo:
    """The display zone tests should use, rather than the machine's local one."""
    return NY
