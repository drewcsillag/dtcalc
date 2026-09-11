"""Tests for the coverage badge script.

The script's whole job is to stop the badge from lying, so its asymmetry is
worth pinning: overstating fails, understating does not.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.coverage_badge import badge_percent, colour_for, main, write_badge


@pytest.mark.parametrize(
    ("percent", "colour"),
    [
        (100.0, "brightgreen"),
        (95.0, "brightgreen"),
        (94.9, "green"),
        (90.0, "green"),
        (89.9, "yellowgreen"),
        (80.0, "yellowgreen"),
        (79.9, "yellow"),
        (70.0, "yellow"),
        (69.9, "orange"),
        (60.0, "orange"),
        (59.9, "red"),
        (0.0, "red"),
    ],
)
def test_colour_thresholds(percent: float, colour: str) -> None:
    assert colour_for(percent) == colour


def test_write_badge_produces_a_shields_endpoint_payload(tmp_path: Path) -> None:
    badge = tmp_path / "coverage.json"
    write_badge(badge, 93.7)
    payload = json.loads(badge.read_text())
    assert payload == {
        "schemaVersion": 1,
        "label": "coverage",
        "message": "93.7%",
        "color": "green",
    }


def test_badge_percent_reads_back_what_was_written(tmp_path: Path) -> None:
    badge = tmp_path / "coverage.json"
    write_badge(badge, 88.25)
    assert badge_percent(badge) == 88.2


def test_badge_percent_of_a_missing_or_broken_file_is_none(tmp_path: Path) -> None:
    assert badge_percent(tmp_path / "nope.json") is None
    broken = tmp_path / "broken.json"
    broken.write_text('{"message": "not a number"}')
    assert badge_percent(broken) is None


def report(tmp_path: Path, percent: float) -> Path:
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps({"totals": {"percent_covered": percent}}))
    return path


def run_check(tmp_path: Path, actual: float, claimed: float, floor: float = 90.0) -> int:
    badge = tmp_path / "badge.json"
    write_badge(badge, claimed)
    return main(
        [
            "--report",
            str(report(tmp_path, actual)),
            "--badge",
            str(badge),
            "--floor",
            str(floor),
            "--check",
        ]
    )


def test_a_consistent_badge_passes(tmp_path: Path) -> None:
    assert run_check(tmp_path, actual=93.7, claimed=93.7) == 0


def test_a_badge_that_overstates_fails(tmp_path: Path) -> None:
    """The only genuinely bad state: the badge claiming more than reality."""
    assert run_check(tmp_path, actual=93.7, claimed=99.9) == 1


def test_a_badge_that_understates_passes(tmp_path: Path) -> None:
    """So that improving coverage never breaks the build."""
    assert run_check(tmp_path, actual=93.7, claimed=80.0) == 0


def test_coverage_below_the_floor_fails(tmp_path: Path) -> None:
    assert run_check(tmp_path, actual=85.0, claimed=85.0, floor=90.0) == 1


def test_a_missing_report_fails(tmp_path: Path) -> None:
    assert main(["--report", str(tmp_path / "nope.json"), "--check"]) == 1


def test_a_missing_badge_fails_the_check(tmp_path: Path) -> None:
    assert (
        main(
            [
                "--report",
                str(report(tmp_path, 93.7)),
                "--badge",
                str(tmp_path / "absent.json"),
                "--check",
            ]
        )
        == 1
    )


def test_generate_mode_writes_the_measured_value(tmp_path: Path) -> None:
    badge = tmp_path / "badge.json"
    assert main(["--report", str(report(tmp_path, 91.234)), "--badge", str(badge)]) == 0
    assert badge_percent(badge) == 91.2


def test_the_committed_badge_matches_the_repository_state() -> None:
    """The badge in the repo is readable and plausible."""
    committed = Path(".github/badges/coverage.json")
    assert committed.exists()
    percent = badge_percent(committed)
    assert percent is not None
    assert 0.0 <= percent <= 100.0
