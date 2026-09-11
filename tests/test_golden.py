"""Golden transcript tests.

Each ``tests/golden/<name>.in`` is fed through the CLI in transcript mode and
the whole of stdout is compared against ``<name>.out``.  This is the test type
that pins the *user-visible* contract — prompts, result formatting, error
messages with their carets, and state carried between lines — rather than any
internal representation.

The clock and display zone are frozen through ``DTCALC_NOW`` and
``DTCALC_TZ``, which is the only reason a transcript can mention ``now``.

To regenerate after an intentional change::

    UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py

Then read the diff.  A change you cannot explain is a bug, not a stale file.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

GOLDEN = Path(__file__).parent / "golden"
CASES = sorted(path.stem for path in GOLDEN.glob("*.in"))

FROZEN_ENV = {
    "DTCALC_NOW": "2026-05-23T12:15:13",
    "DTCALC_TZ": "America/New_York",
    "NO_COLOR": "1",
}


def _run(source: str) -> str:
    """Run the CLI in-process with ``source`` on stdin, capturing stdout."""
    from dtcalc.cli import main

    class _Pipe(io.StringIO):
        def isatty(self) -> bool:
            return False

    saved_stdin, saved_stdout, saved_stderr = sys.stdin, sys.stdout, sys.stderr
    saved_env = {key: os.environ.get(key) for key in FROZEN_ENV}
    captured = io.StringIO()
    try:
        os.environ.update(FROZEN_ENV)
        sys.stdin = _Pipe(source)
        sys.stdout = captured
        # Transcript mode routes errors to stdout, so one stream holds the
        # whole session.
        sys.stderr = captured
        main(["--transcript"])
    finally:
        sys.stdin, sys.stdout, sys.stderr = saved_stdin, saved_stdout, saved_stderr
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return captured.getvalue()


@pytest.mark.parametrize("case", CASES)
def test_golden_transcript(case: str) -> None:
    source = (GOLDEN / f"{case}.in").read_text()
    actual = _run(source)
    expected_path = GOLDEN / f"{case}.out"

    if os.environ.get("UPDATE_GOLDEN"):
        expected_path.write_text(actual)
        pytest.skip(f"regenerated {expected_path.name}")

    assert expected_path.exists(), (
        f"{expected_path.name} is missing; run UPDATE_GOLDEN=1 pytest to create it"
    )
    assert actual == expected_path.read_text()


def test_there_is_at_least_one_case() -> None:
    assert CASES


def test_transcripts_contain_no_escape_sequences() -> None:
    """NO_COLOR keeps the goldens readable and diffable."""
    for case in CASES:
        assert "\x1b" not in (GOLDEN / f"{case}.out").read_text()


def test_the_installed_entry_point_agrees_with_the_in_process_run() -> None:
    """Guards against the CLI working only when imported, not when executed."""
    source = "1h + 1h\nnow\n"
    result = subprocess.run(
        [sys.executable, "-m", "dtcalc", "--transcript"],
        input=source,
        capture_output=True,
        text=True,
        env={**os.environ, **FROZEN_ENV},
        check=True,
    )
    assert result.stdout == _run(source)
