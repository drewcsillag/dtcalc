"""The size budget for the web build: the first load stays under what was agreed."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest
from scripts.check_web_budget import MAX_TRANSFER, Sizes, check, measure


def _files(root: Path, **named: bytes) -> Path:
    for name, data in named.items():
        (root / name).write_bytes(data)
    return root


def test_measure_counts_raw_and_compressed_bytes(tmp_path: Path) -> None:
    data = b"abc" * 1000
    sizes = measure(_files(tmp_path, a=data))
    assert sizes.raw == len(data)
    assert sizes.transfer == len(gzip.compress(data, 9))
    assert sizes.files == 1


def test_measure_walks_subdirectories(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    _files(tmp_path, a=b"x")
    (tmp_path / "sub" / "b").write_bytes(b"y")
    assert measure(tmp_path).files == 2


def test_measure_refuses_an_empty_or_missing_build(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="nothing to measure"):
        measure(tmp_path)
    with pytest.raises(SystemExit, match="nothing to measure"):
        measure(tmp_path / "missing")


def test_within_budget_passes_and_reports() -> None:
    message = check(Sizes(files=3, raw=14_000_000, transfer=6_600_000))
    assert "6.6 MB" in message


def test_over_the_transfer_budget_fails() -> None:
    with pytest.raises(SystemExit, match="over the budget"):
        check(Sizes(files=3, raw=20_000_000, transfer=MAX_TRANSFER + 1))


def test_the_budget_is_the_agreed_ten_megabytes() -> None:
    assert MAX_TRANSFER == 10_000_000
