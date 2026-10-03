"""Fail if the web build's first load outgrows its budget.

The first visit downloads everything (the service worker precaches it all), so
the figure that matters is the compressed total.  GitHub Pages compresses on
the wire; gzip at level 9 here is a close, slightly pessimistic stand-in.

Run through ``make web-budget`` after ``make web-build``.
"""

from __future__ import annotations

import gzip
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

__all__ = ["MAX_TRANSFER", "Sizes", "check", "measure"]

DIST: Final = Path(__file__).resolve().parent.parent / "web" / "dist"

# The agreed ceiling for a first load: 10 MB.  Pyodide is most of it, so this
# moves when Pyodide does, and growing past it is a decision, not an accident.
MAX_TRANSFER: Final = 10_000_000


@dataclass(frozen=True)
class Sizes:
    files: int
    raw: int
    transfer: int


def measure(root: Path) -> Sizes:
    paths = [path for path in sorted(root.rglob("*")) if path.is_file()] if root.is_dir() else []
    if not paths:
        raise SystemExit(f"nothing to measure in {root}; run `make web-build` first")
    raw = transfer = 0
    for path in paths:
        data = path.read_bytes()
        raw += len(data)
        transfer += len(gzip.compress(data, 9))
    return Sizes(files=len(paths), raw=raw, transfer=transfer)


def _megabytes(size: int) -> str:
    return f"{size / 1_000_000:.1f} MB"


def check(sizes: Sizes) -> str:
    summary = (
        f"{sizes.files} files, {_megabytes(sizes.raw)} on disk, "
        f"{_megabytes(sizes.transfer)} compressed (budget {_megabytes(MAX_TRANSFER)})"
    )
    if sizes.transfer > MAX_TRANSFER:
        raise SystemExit(f"web build is over the budget: {summary}")
    return summary


if __name__ == "__main__":
    sys.stdout.write(check(measure(DIST)) + "\n")
