"""Tests for timezone name resolution and local-zone detection."""

from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from dtcalc.errors import DtcalcError
from dtcalc.zones import local_zone, resolve_zone, search_zones


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("America/Los_Angeles", "America/Los_Angeles"),
        ("Europe/London", "Europe/London"),
        ("Asia/Tokyo", "Asia/Tokyo"),
    ],
)
def test_exact_iana_names_resolve(name: str, expected: str) -> None:
    assert str(resolve_zone(name)) == expected


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("SanFrancisco", "America/Los_Angeles"),
        ("san_francisco", "America/Los_Angeles"),
        ("San Francisco", "America/Los_Angeles"),
        ("sf", "America/Los_Angeles"),
        ("SF", "America/Los_Angeles"),
        ("la", "America/Los_Angeles"),
        ("nyc", "America/New_York"),
        ("NewYork", "America/New_York"),
        ("new-york", "America/New_York"),
        ("chicago", "America/Chicago"),
        ("denver", "America/Denver"),
        ("seattle", "America/Los_Angeles"),
        ("london", "Europe/London"),
        ("paris", "Europe/Paris"),
        ("berlin", "Europe/Berlin"),
        ("amsterdam", "Europe/Amsterdam"),
        ("telaviv", "Asia/Jerusalem"),
        ("tel aviv", "Asia/Jerusalem"),
        ("bangalore", "Asia/Kolkata"),
        ("india", "Asia/Kolkata"),
        ("singapore", "Asia/Singapore"),
        ("tokyo", "Asia/Tokyo"),
        ("sydney", "Australia/Sydney"),
        ("utc", "UTC"),
        ("z", "UTC"),
    ],
)
def test_curated_aliases_resolve(alias: str, expected: str) -> None:
    assert str(resolve_zone(alias)) == expected


@pytest.mark.parametrize(
    ("abbreviation", "expected"),
    [
        ("PST", "America/Los_Angeles"),
        ("PDT", "America/Los_Angeles"),
        ("EST", "America/New_York"),
        ("EDT", "America/New_York"),
        ("CST", "America/Chicago"),
        ("MST", "America/Denver"),
        ("CET", "Europe/Berlin"),
        ("GMT", "Europe/London"),
    ],
)
def test_abbreviations_resolve_to_the_city_zone_not_the_fixed_offset_relic(
    abbreviation: str, expected: str
) -> None:
    """`EST` is also a real IANA zone with no DST, which is never what you mean."""
    assert str(resolve_zone(abbreviation)) == expected


def test_a_unique_substring_match_resolves() -> None:
    assert str(resolve_zone("Reykjavik")) == "Atlantic/Reykjavik"


def test_an_ambiguous_name_errors_and_lists_the_candidates() -> None:
    with pytest.raises(DtcalcError) as excinfo:
        resolve_zone("Argentina")
    message = excinfo.value.message
    assert "ambiguous" in message
    assert "America/Argentina/Buenos_Aires" in message


def test_an_unknown_name_errors_without_candidates() -> None:
    with pytest.raises(DtcalcError, match="unknown timezone"):
        resolve_zone("Atlantis")


def test_ambiguity_error_truncates_a_very_long_candidate_list() -> None:
    with pytest.raises(DtcalcError) as excinfo:
        resolve_zone("America")
    assert "more" in excinfo.value.message


def test_search_finds_zones_by_substring() -> None:
    assert "Asia/Tokyo" in search_zones("tokyo")
    assert search_zones("tokyo") == sorted(search_zones("tokyo"))


def test_search_includes_alias_targets() -> None:
    assert "America/Los_Angeles" in search_zones("angeles")


def test_search_for_nothing_returns_nothing() -> None:
    assert search_zones("zzzznope") == []


# --------------------------------------------------------------------------
# 2.1a  local zone detection
# --------------------------------------------------------------------------


def test_tz_environment_variable_wins() -> None:
    assert local_zone(env={"TZ": "Asia/Tokyo"}, localtime_path=None) == ZoneInfo("Asia/Tokyo")


def test_tz_environment_variable_accepts_an_alias() -> None:
    assert local_zone(env={"TZ": "sf"}, localtime_path=None) == ZoneInfo("America/Los_Angeles")


def test_a_bogus_tz_value_errors_rather_than_silently_becoming_utc() -> None:
    with pytest.raises(DtcalcError, match="TZ"):
        local_zone(env={"TZ": "Atlantis"}, localtime_path=None)


def test_the_localtime_symlink_is_read_when_tz_is_unset(tmp_path: Path) -> None:
    target = tmp_path / "zoneinfo" / "America" / "New_York"
    target.parent.mkdir(parents=True)
    target.touch()
    link = tmp_path / "localtime"
    link.symlink_to(target)
    assert local_zone(env={}, localtime_path=link) == ZoneInfo("America/New_York")


def test_a_missing_symlink_falls_back_to_utc(tmp_path: Path) -> None:
    assert local_zone(env={}, localtime_path=tmp_path / "nope") == ZoneInfo("UTC")


def test_a_symlink_pointing_somewhere_unexpected_falls_back_to_utc(tmp_path: Path) -> None:
    target = tmp_path / "somewhere" / "else"
    target.parent.mkdir(parents=True)
    target.touch()
    link = tmp_path / "localtime"
    link.symlink_to(target)
    assert local_zone(env={}, localtime_path=link) == ZoneInfo("UTC")


def test_detection_on_this_machine_produces_an_iana_name() -> None:
    """Not an assertion about *which* zone — just that we get a real name."""
    assert str(local_zone()) in {"UTC"} | set(search_zones("/"))
