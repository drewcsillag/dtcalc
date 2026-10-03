"""The web build: pinned downloads, and the service worker it stamps."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from scripts.build_web import content_version, precache_files, stamp_service_worker, verified


def test_matching_hash_passes_the_bytes_through() -> None:
    data = b"wheel"
    assert verified(data, hashlib.sha256(data).hexdigest(), "x") == data


def test_a_different_hash_aborts_the_build() -> None:
    with pytest.raises(SystemExit, match="does not match the pinned"):
        verified(b"tampered", hashlib.sha256(b"wheel").hexdigest(), "x")


TEMPLATE = 'const VERSION = "__VERSION__";\nconst FILES = __FILES__;\n'


def _site(root: Path) -> Path:
    (root / "wheels").mkdir(parents=True)
    (root / "index.html").write_text("<html>")
    (root / "app.js").write_text("run()")
    (root / "sw.js").write_text("self")
    (root / "wheels" / "dtcalc.whl").write_bytes(b"wheel")
    (root / "wheels" / ".gitignore").write_text("*")
    return root


def test_the_precache_lists_every_file_but_the_service_worker_and_dotfiles(tmp_path: Path) -> None:
    files = precache_files(_site(tmp_path))
    assert files == ["app.js", "index.html", "wheels/dtcalc.whl"]


def test_the_version_follows_the_content(tmp_path: Path) -> None:
    root = _site(tmp_path)
    before = content_version(root, precache_files(root))
    assert before == content_version(root, precache_files(root))

    (root / "app.js").write_text("run(2)")
    assert content_version(root, precache_files(root)) != before


def test_the_version_follows_the_file_names(tmp_path: Path) -> None:
    root = _site(tmp_path)
    before = content_version(root, precache_files(root))
    (root / "wheels" / "dtcalc.whl").rename(root / "wheels" / "other.whl")
    assert content_version(root, precache_files(root)) != before


def test_stamping_fills_in_the_version_and_the_file_list() -> None:
    stamped = stamp_service_worker(TEMPLATE, ["a.js", "b/c.wasm"], "abc123")
    assert 'const VERSION = "abc123";' in stamped
    assert 'const FILES = ["a.js", "b/c.wasm"];' in stamped
    assert "__" not in stamped


def test_a_template_without_its_placeholders_is_refused() -> None:
    with pytest.raises(SystemExit, match="placeholder"):
        stamp_service_worker("const x = 1;", ["a.js"], "abc123")


def test_file_names_are_embedded_as_json_strings() -> None:
    stamped = stamp_service_worker(TEMPLATE, ['we"ird.js'], "v")
    (line,) = [row for row in stamped.splitlines() if row.startswith("const FILES")]
    assert json.loads(line.removeprefix("const FILES = ").removesuffix(";")) == ['we"ird.js']
