"""Helpers shared across the test suite.

Kept out of ``conftest.py`` so they can be imported by name rather than only
injected as fixtures.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

__all__ = ["NY", "TEST_NOW", "TOKYO", "UTC_ZONE", "at"]

NY = ZoneInfo("America/New_York")
TOKYO = ZoneInfo("Asia/Tokyo")
UTC_ZONE = ZoneInfo("UTC")

# 12:15:13 on 2026-05-23 in New York, which is the timestamp from the original
# feature request.  Choosing it means the worked examples in the request are
# also the examples the frozen clock produces.
TEST_NOW = datetime(2026, 5, 23, 12, 15, 13, tzinfo=NY)


def at(zone: ZoneInfo, iso: str) -> datetime:
    """Build an aware datetime from an ISO string interpreted in ``zone``."""
    return datetime.fromisoformat(iso).replace(tzinfo=zone)
