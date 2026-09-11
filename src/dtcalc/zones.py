"""Timezone name resolution.

Resolution order, and the reason for it:

1. **An exact IANA name containing a ``/``** — ``America/Los_Angeles``.
   Unambiguous, so it wins outright.
2. **The curated alias table** — cities you actually name, plus the common
   abbreviations.  This deliberately sits *above* the bare IANA names so that
   ``EST`` means US Eastern with daylight saving, rather than the fixed-offset
   ``EST`` zone that the tz database still carries and nobody means.
3. **Any other exact IANA name** — ``UTC``, ``Zulu``, ``Iran``.
4. **A unique case-insensitive substring match** — ``Reykjavik`` finds
   ``Atlantic/Reykjavik``.  Only when exactly one zone matches; several
   matches is an error that lists them rather than a guess.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo, available_timezones

from dtcalc.errors import DtcalcError

__all__ = ["CURATED_ALIASES", "all_zone_names", "local_zone", "resolve_zone", "search_zones"]

_LOCALTIME = Path("/etc/localtime")
_ZONEINFO_MARKER = "zoneinfo"
_MAX_LISTED_CANDIDATES: Final = 8

# Cities, in the spellings a person actually types.  Keys are normalized by
# _normalize, so case, spaces, underscores and hyphens are all equivalent.
_CITY_ALIASES: Final[dict[str, str]] = {
    "sf": "America/Los_Angeles",
    "sanfrancisco": "America/Los_Angeles",
    "sanfran": "America/Los_Angeles",
    "la": "America/Los_Angeles",
    "losangeles": "America/Los_Angeles",
    "seattle": "America/Los_Angeles",
    "portland": "America/Los_Angeles",
    "pacific": "America/Los_Angeles",
    "denver": "America/Denver",
    "mountain": "America/Denver",
    "chicago": "America/Chicago",
    "central": "America/Chicago",
    "nyc": "America/New_York",
    "newyork": "America/New_York",
    "eastern": "America/New_York",
    "boston": "America/New_York",
    "london": "Europe/London",
    "paris": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "amsterdam": "Europe/Amsterdam",
    "telaviv": "Asia/Jerusalem",
    "israel": "Asia/Jerusalem",
    "bangalore": "Asia/Kolkata",
    "bengaluru": "Asia/Kolkata",
    "india": "Asia/Kolkata",
    "singapore": "Asia/Singapore",
    "tokyo": "Asia/Tokyo",
    "japan": "Asia/Tokyo",
    "sydney": "Australia/Sydney",
    "utc": "UTC",
    "z": "UTC",
    "zulu": "UTC",
}

# Abbreviations map to the city zone, standard and daylight forms alike, so
# that `PST` in December and `PDT` in July both just mean "the west coast".
_ABBREVIATION_ALIASES: Final[dict[str, str]] = {
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "mst": "America/Denver",
    "mdt": "America/Denver",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "est": "America/New_York",
    "edt": "America/New_York",
    "gmt": "Europe/London",
    "bst": "Europe/London",
    "cet": "Europe/Berlin",
    "cest": "Europe/Berlin",
    "ist": "Asia/Kolkata",
    "jst": "Asia/Tokyo",
}

_ALIASES: Final[dict[str, str]] = {**_CITY_ALIASES, **_ABBREVIATION_ALIASES}


# Readable spellings of the curated aliases, for tab completion.  The lookup
# table is normalized for matching; these are what a person would type.
CURATED_ALIASES: Final[tuple[str, ...]] = (
    "SanFrancisco",
    "LosAngeles",
    "Seattle",
    "Portland",
    "Denver",
    "Chicago",
    "NewYork",
    "Boston",
    "London",
    "Paris",
    "Berlin",
    "Amsterdam",
    "TelAviv",
    "Bangalore",
    "India",
    "Singapore",
    "Tokyo",
    "Sydney",
    "UTC",
)


def all_zone_names() -> list[str]:
    """Every IANA zone name, sorted."""
    return sorted(available_timezones())


def _normalize(name: str) -> str:
    """Fold case and drop the separators people vary on."""
    return "".join(ch for ch in name.lower() if ch.isalnum())


def resolve_zone(name: str) -> ZoneInfo:
    """Resolve a zone name, alias or abbreviation to a :class:`ZoneInfo`."""
    known = available_timezones()

    if "/" in name and name in known:
        return ZoneInfo(name)

    alias = _ALIASES.get(_normalize(name))
    if alias is not None:
        return ZoneInfo(alias)

    if name in known:
        return ZoneInfo(name)

    matches = search_zones(name)
    if len(matches) == 1:
        return ZoneInfo(matches[0])
    if matches:
        listed = ", ".join(matches[:_MAX_LISTED_CANDIDATES])
        if len(matches) > _MAX_LISTED_CANDIDATES:
            listed += f", and {len(matches) - _MAX_LISTED_CANDIDATES} more"
        raise DtcalcError(f"ambiguous timezone {name!r}; did you mean one of: {listed}")
    raise DtcalcError(f"unknown timezone {name!r}")


def search_zones(substring: str) -> list[str]:
    """Every IANA zone whose name contains ``substring``, case-insensitively."""
    needle = substring.lower()
    return sorted(zone for zone in available_timezones() if needle in zone.lower())


def local_zone(
    *,
    env: Mapping[str, str] | None = None,
    localtime_path: Path | None = _LOCALTIME,
) -> ZoneInfo:
    """Detect the machine's local zone as an IANA zone.

    There is no stdlib way to do this: ``datetime.now().astimezone().tzinfo``
    yields the abbreviation ``EDT``, not ``America/New_York``.  So honour
    ``TZ`` if set, otherwise read where ``/etc/localtime`` points, otherwise
    fall back to UTC.

    Both inputs are parameters rather than globals so that tests can drive
    every branch without touching the environment.
    """
    environment = os.environ if env is None else env

    tz = environment.get("TZ")
    if tz:
        try:
            return resolve_zone(tz)
        except DtcalcError as exc:
            raise DtcalcError(f"TZ is set to {tz!r}, which is not a timezone") from exc

    if localtime_path is not None:
        detected = _zone_from_localtime(localtime_path)
        if detected is not None:
            return detected

    return ZoneInfo("UTC")


def _zone_from_localtime(path: Path) -> ZoneInfo | None:
    """Read an IANA name out of a ``/etc/localtime``-style symlink."""
    try:
        target = path.resolve(strict=True)
    except OSError:
        return None

    parts = target.parts
    if _ZONEINFO_MARKER not in parts:
        return None
    candidate = "/".join(parts[parts.index(_ZONEINFO_MARKER) + 1 :])
    if candidate in available_timezones():
        return ZoneInfo(candidate)
    return None
