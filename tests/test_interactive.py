"""Interactive tests driven through a real pty.

These cover the one part of the REPL that cannot be tested as a function: the
readline wiring.  Tab completion has real logic behind it and is the reason
this file exists; history recall and the two interrupts are smoke-tested so a
regression in the loop shows up.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from typing import Any

import pytest

# pexpect ships no type stubs, so the spawned child is genuinely untyped here.
pexpect: Any = pytest.importorskip("pexpect")

PROMPT = "dtcalc> "
TIMEOUT = 15

FROZEN_ENV = {
    "DTCALC_NOW": "2026-05-23T12:15:13",
    "DTCALC_TZ": "America/New_York",
    "NO_COLOR": "1",
    "TERM": "dumb",
}


@pytest.fixture
def repl() -> Iterator[Any]:
    """A dtcalc REPL on a pseudo-terminal, shut down at the end of the test."""
    child = pexpect.spawn(
        sys.executable,
        ["-m", "dtcalc"],
        env={**os.environ, **FROZEN_ENV},
        encoding="utf-8",
        timeout=TIMEOUT,
        dimensions=(24, 120),
    )
    child.expect_exact(PROMPT)
    yield child
    if child.isalive():
        child.terminate(force=True)


def test_the_repl_greets_and_prompts(repl: Any) -> None:
    assert ":help" in repl.before


def test_an_expression_is_evaluated(repl: Any) -> None:
    repl.sendline("1h + 1h")
    repl.expect_exact("2h")
    repl.expect_exact(PROMPT)


def test_state_is_carried_between_lines(repl: Any) -> None:
    repl.sendline("foo = 3h")
    repl.expect_exact(PROMPT)
    repl.sendline("foo + 1h")
    repl.expect_exact("4h")


def test_an_error_does_not_end_the_session(repl: Any) -> None:
    repl.sendline("now +")
    repl.expect_exact("error:")
    repl.expect_exact(PROMPT)
    repl.sendline("1h + 1h")
    repl.expect_exact("2h")


def test_a_meta_command_works(repl: Any) -> None:
    repl.sendline(":fmt human")
    repl.expect_exact("format is now human")
    repl.sendline("now")
    repl.expect_exact("Sat 2026-05-23 12:15:13 EDT")


def test_tab_completes_a_function_name(repl: Any) -> None:
    repl.send("rou\t")
    repl.expect_exact("round")
    repl.sendline("(now, 1h)")
    repl.expect_exact("2026-05-23T12:00:00")


def test_tab_completes_a_variable_name(repl: Any) -> None:
    repl.sendline("fudge = 5m")
    repl.expect_exact(PROMPT)
    repl.send("fud\t")
    repl.expect_exact("fudge")
    repl.sendline("")
    repl.expect_exact("5m")


def test_tab_completes_a_zone_name_after_in(repl: Any) -> None:
    repl.send("now in Toky\t")
    repl.expect_exact("Tokyo")
    repl.sendline("")
    repl.expect_exact("Asia/Tokyo")


def test_history_recalls_the_previous_line(repl: Any) -> None:
    repl.sendline("1h + 1h")
    repl.expect_exact("2h")
    repl.expect_exact(PROMPT)
    repl.send("\x1b[A")  # up arrow
    repl.sendline("")
    repl.expect_exact("2h")


def test_ctrl_c_abandons_the_line_without_leaving(repl: Any) -> None:
    repl.send("1h + ")
    # Wait for the terminal to echo the partial line before interrupting, so
    # the test exercises "Ctrl-C part way through typing" rather than racing
    # the echo.
    repl.expect_exact("1h + ")
    repl.sendintr()
    repl.expect_exact("^C")
    repl.expect_exact(PROMPT)
    repl.sendline("2h + 2h")
    repl.expect_exact("4h")


def test_ctrl_d_exits_cleanly(repl: Any) -> None:
    repl.sendeof()
    repl.expect(pexpect.EOF)
    repl.close()
    assert repl.exitstatus == 0


def test_the_quit_command_exits_cleanly(repl: Any) -> None:
    repl.sendline(":q")
    repl.expect(pexpect.EOF)
    repl.close()
    assert repl.exitstatus == 0


def test_ctrl_a_reaches_the_start_of_a_wrapped_line() -> None:
    """Regression: a coloured prompt made libedit miscount the prompt width,
    so on a wrapped line Ctrl-A emitted the wrong absolute column and the
    cursor drifted permanently out of step with the buffer."""
    child = pexpect.spawn(
        sys.executable,
        ["-m", "dtcalc"],
        env={**os.environ, **FROZEN_ENV, "TERM": "xterm"},
        encoding="utf-8",
        timeout=TIMEOUT,
        # Narrow enough that the line wraps and libedit must compute an
        # absolute column rather than just backspacing.
        dimensions=(24, 24),
    )
    try:
        child.expect_exact(PROMPT)
        child.send("b" * 30)
        child.expect_exact("b" * 8)
        child.send("\x01")  # Ctrl-A
        # Column 9: eight prompt characters, so the first input column is 9.
        child.expect_exact("\x1b[9G")
    finally:
        if child.isalive():
            child.terminate(force=True)


def test_ctrl_a_then_typing_edits_the_front_of_the_line(repl: Any) -> None:
    repl.sendline("tail = 2h")
    repl.expect_exact(PROMPT)
    repl.send("+ tail")
    repl.expect_exact("+ tail")
    repl.send("\x01")  # Ctrl-A
    repl.send("3h ")
    repl.sendline("")
    repl.expect_exact("5h")


def test_a_date_renders_as_a_date_in_the_repl(repl: Any) -> None:
    repl.sendline("2027-01-03 - 2026-12-24")
    repl.expect_exact("10d")
    repl.sendline("today")
    repl.expect_exact("2026-05-23")


def test_vars_shows_the_kind_column(repl: Any) -> None:
    repl.sendline("birthday = 2026-12-24")
    repl.expect_exact(PROMPT)
    repl.sendline(":vars")
    repl.expect_exact("birthday")
    repl.expect_exact("date")
