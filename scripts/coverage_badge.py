#!/usr/bin/env python
"""Generate, or verify, the README's coverage badge.

The badge is a small JSON file committed to the repository, which shields.io
reads through its endpoint API. That keeps the whole thing self-contained: no
third-party coverage service, and no token in CI.

Honesty is enforced asymmetrically, which is the point of the design:

* ``--check`` fails when the committed badge claims **more** coverage than was
  actually measured. A badge that lies upward is the only genuinely bad state.
* A badge that understates is allowed, so improving coverage never breaks the
  build. It prints a nudge to regenerate instead.
* ``--check`` also fails when coverage falls below the floor, so it cannot rot
  quietly between badge updates.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BADGE_PATH = Path(".github/badges/coverage.json")

# (minimum percentage, shields colour)
COLOURS: tuple[tuple[float, str], ...] = (
    (95.0, "brightgreen"),
    (90.0, "green"),
    (80.0, "yellowgreen"),
    (70.0, "yellow"),
    (60.0, "orange"),
    (0.0, "red"),
)

# Understating by more than this is worth a nudge, but never a failure.
STALE_TOLERANCE = 0.5


def colour_for(percent: float) -> str:
    for threshold, colour in COLOURS:
        if percent >= threshold:
            return colour
    return "red"  # pragma: no cover - the table ends at 0.0


def measured_percent(report: Path) -> float:
    """Read the total from a ``coverage json`` report."""
    data = json.loads(report.read_text())
    percent = data["totals"]["percent_covered"]
    assert isinstance(percent, int | float)
    return round(float(percent), 1)


def badge_percent(path: Path) -> float | None:
    if not path.exists():
        return None
    message = json.loads(path.read_text()).get("message", "")
    try:
        return float(str(message).rstrip("%"))
    except ValueError:
        return None


def write_badge(path: Path, percent: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    badge = {
        "schemaVersion": 1,
        "label": "coverage",
        "message": f"{percent:.1f}%",
        "color": colour_for(percent),
    }
    path.write_text(json.dumps(badge, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=Path("coverage.json"))
    parser.add_argument("--badge", type=Path, default=BADGE_PATH)
    parser.add_argument("--floor", type=float, default=90.0)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify rather than rewrite: fail if the badge overstates, or if "
        "coverage is below the floor",
    )
    args = parser.parse_args(argv)

    if not args.report.exists():
        print(f"error: no coverage report at {args.report}", file=sys.stderr)
        return 1

    actual = measured_percent(args.report)

    if not args.check:
        write_badge(args.badge, actual)
        print(f"coverage {actual:.1f}% -> {args.badge}")
        return 0

    status = 0

    if actual < args.floor:
        print(
            f"error: coverage {actual:.1f}% is below the {args.floor:.1f}% floor",
            file=sys.stderr,
        )
        status = 1

    claimed = badge_percent(args.badge)
    if claimed is None:
        print(f"error: no readable badge at {args.badge}; run `make coverage`", file=sys.stderr)
        return 1

    if claimed > actual:
        print(
            f"error: the badge claims {claimed:.1f}% but coverage is "
            f"{actual:.1f}%; run `make coverage` to correct it",
            file=sys.stderr,
        )
        status = 1
    elif actual - claimed > STALE_TOLERANCE:
        print(
            f"note: coverage has improved to {actual:.1f}% but the badge still "
            f"says {claimed:.1f}%; run `make coverage` when convenient"
        )
    else:
        print(f"coverage {actual:.1f}%, badge says {claimed:.1f}% - consistent")

    return status


if __name__ == "__main__":
    raise SystemExit(main())
