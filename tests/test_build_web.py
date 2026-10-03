"""The web build refuses a download that does not match its pinned hash."""

from __future__ import annotations

import hashlib

import pytest
from scripts.build_web import verified


def test_matching_hash_passes_the_bytes_through() -> None:
    data = b"wheel"
    assert verified(data, hashlib.sha256(data).hexdigest(), "x") == data


def test_a_different_hash_aborts_the_build() -> None:
    with pytest.raises(SystemExit, match="does not match the pinned"):
        verified(b"tampered", hashlib.sha256(b"wheel").hexdigest(), "x")
