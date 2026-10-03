"""Assemble ``web/dist``: Pyodide, the dtcalc wheel and the tzdata wheel.

Everything the browser needs is copied or built here and nothing is fetched
at runtime, which is what lets the page work offline and from any host.

The one network access is the ``tzdata`` wheel.  It is pinned by version *and*
sha256, so a changed or tampered file fails the build rather than shipping.
Pyodide's own files come from the pinned ``pyodide`` npm package.

Run through ``make web-build``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Final

__all__ = ["build", "content_version", "precache_files", "stamp_service_worker", "verified"]

ROOT: Final = Path(__file__).resolve().parent.parent
WEB: Final = ROOT / "web"
DIST: Final = WEB / "dist"
CACHE: Final = WEB / ".cache"

TZDATA_FILE: Final = "tzdata-2026.5-py2.py3-none-any.whl"
TZDATA_URL: Final = (
    "https://files.pythonhosted.org/packages/94/21/"
    "1e5995a1c920cce14e4bffae20c665ec10e7ed03ab25e006cd741092b718/" + TZDATA_FILE
)
TZDATA_SHA256: Final = "b683bd1b6659ddcd810ff02ad09ba821d4bf1065072805063eb35c49617905ac"

# The files Pyodide needs at runtime; the rest of the npm package is typings,
# a console demo and source maps.
PYODIDE_FILES: Final = (
    "pyodide.mjs",
    "pyodide.asm.mjs",
    "pyodide.asm.wasm",
    "python_stdlib.zip",
    "pyodide-lock.json",
)


def verified(data: bytes, expected_sha256: str, label: str) -> bytes:
    """Return ``data`` if its sha256 matches, else refuse."""
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected_sha256:
        raise SystemExit(f"{label}: sha256 {actual} does not match the pinned {expected_sha256}")
    return data


def _tzdata_wheel() -> bytes:
    cached = CACHE / TZDATA_FILE
    if cached.exists():
        return verified(cached.read_bytes(), TZDATA_SHA256, TZDATA_FILE)
    with urllib.request.urlopen(TZDATA_URL, timeout=60) as response:
        data = verified(response.read(), TZDATA_SHA256, TZDATA_FILE)
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(data)
    return data


def _build_wheel(into: Path) -> Path:
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(into)],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    (wheel,) = into.glob("dtcalc_cli-*.whl")
    return wheel


def _copy_pyodide(into: Path) -> None:
    source = WEB / "node_modules" / "pyodide"
    if not source.is_dir():
        raise SystemExit("web/node_modules/pyodide is missing; run `npm ci` in web/ first")
    into.mkdir(parents=True)
    for name in PYODIDE_FILES:
        shutil.copy2(source / name, into / name)


def _copy_site(into: Path) -> None:
    """Copy the hand-written page, scripts, styles and icons next to the generated files."""
    shutil.copytree(WEB / "src", into, dirs_exist_ok=True)


SERVICE_WORKER: Final = "sw.js"


def precache_files(root: Path) -> list[str]:
    """Every file under ``root`` the offline copy needs, as sorted relative URLs."""
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != SERVICE_WORKER and not path.name.startswith(".")
    )


def content_version(root: Path, files: list[str]) -> str:
    """A short hash of the names and contents, so any change yields a new version."""
    digest = hashlib.sha256()
    for name in files:
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update((root / name).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def stamp_service_worker(template: str, files: list[str], version: str) -> str:
    """Fill the worker's version and file list; refuse a template that lacks the slots."""
    if "__VERSION__" not in template or "__FILES__" not in template:
        raise SystemExit("the service worker template is missing its placeholder")
    return template.replace("__VERSION__", version).replace("__FILES__", json.dumps(files))


def _stamp(root: Path) -> None:
    worker = root / SERVICE_WORKER
    files = precache_files(root)
    worker.write_text(stamp_service_worker(worker.read_text(), files, content_version(root, files)))


def build() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    wheels = DIST / "wheels"
    wheels.mkdir(parents=True)

    dtcalc_wheel = _build_wheel(wheels)
    (wheels / TZDATA_FILE).write_bytes(_tzdata_wheel())
    _copy_pyodide(DIST / "pyodide")
    _copy_site(DIST)

    # The order is the install order; the manifest is what the page and the
    # service worker both read, so neither hard-codes a version.
    (DIST / "wheels.json").write_text(json.dumps([TZDATA_FILE, dtcalc_wheel.name]) + "\n")

    # Last, so the precache list covers every file above.
    _stamp(DIST)


if __name__ == "__main__":
    build()
    sys.stdout.write(f"built {DIST}\n")
