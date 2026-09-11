"""Tests for line execution and meta-command dispatch.

Both are pure functions of ``(line, env)``, so the whole interactive surface
except readline itself is testable without a terminal.
"""

from __future__ import annotations

import pytest

from dtcalc.clock import FixedClock
from dtcalc.env import Env
from dtcalc.format import PLAIN
from dtcalc.session import Outcome, execute_line, help_text

from .support import NY, TEST_NOW


@pytest.fixture
def env() -> Env:
    return Env(clock=FixedClock(TEST_NOW), zone=NY)


def run(env: Env, line: str) -> tuple[Outcome, list[str]]:
    result = execute_line(line, env, PLAIN)
    return result.outcome, list(result.lines)


def test_an_expression_produces_a_result() -> None:
    env = Env(clock=FixedClock(TEST_NOW), zone=NY)
    assert run(env, "1h + 1h") == (Outcome.OK, ["2h"])


@pytest.mark.parametrize("line", ["", "   ", "# a comment", "  # indented comment"])
def test_lines_with_nothing_to_evaluate_produce_nothing(env: Env, line: str) -> None:
    assert run(env, line) == (Outcome.NOTHING, [])


def test_an_error_is_reported_with_a_caret(env: Env) -> None:
    outcome, lines = run(env, "now +")
    assert outcome is Outcome.ERROR
    assert "^" in "\n".join(lines)


def test_a_lexer_error_is_reported_too(env: Env) -> None:
    outcome, lines = run(env, "now + $")
    assert outcome is Outcome.ERROR
    assert "unexpected character" in lines[0]


# --------------------------------------------------------------------------
# meta-commands
# --------------------------------------------------------------------------


@pytest.mark.parametrize("line", [":q", ":quit", ":exit"])
def test_quit(env: Env, line: str) -> None:
    assert run(env, line) == (Outcome.QUIT, [])


def test_help_lists_the_commands(env: Env) -> None:
    outcome, lines = run(env, ":help")
    assert outcome is Outcome.OK
    assert lines == help_text()
    assert any(":fmt" in line for line in lines)


def test_help_explains_the_ladder_rule(env: Env) -> None:
    """The single most surprising thing about the language belongs in :help."""
    assert any("24h" in line and "1d" in line for line in help_text())


def test_vars_when_empty(env: Env) -> None:
    assert run(env, ":vars") == (Outcome.OK, ["(no variables set)"])


def test_vars_lists_what_is_set(env: Env) -> None:
    run(env, "a = 3h")
    run(env, "bb = 1d")
    outcome, lines = run(env, ":vars")
    assert outcome is Outcome.OK
    assert lines == ["a   3h", "bb  1d"]


def test_zones_searches(env: Env) -> None:
    outcome, lines = run(env, ":zones tokyo")
    assert outcome is Outcome.OK
    assert lines == ["Asia/Tokyo"]


def test_zones_truncates_a_long_list(env: Env) -> None:
    outcome, lines = run(env, ":zones america")
    assert outcome is Outcome.OK
    assert lines[-1].startswith("... and ")


def test_zones_with_no_match(env: Env) -> None:
    assert run(env, ":zones zzznope") == (Outcome.OK, ["no timezone matches 'zzznope'"])


def test_zones_needs_an_argument(env: Env) -> None:
    outcome, lines = run(env, ":zones")
    assert outcome is Outcome.ERROR
    assert "needs something to search for" in lines[0]


def test_tz_reports_the_current_zone(env: Env) -> None:
    assert run(env, ":tz") == (Outcome.OK, ["display zone is America/New_York"])


def test_tz_sets_the_zone_and_affects_later_results(env: Env) -> None:
    outcome, lines = run(env, ":tz Tokyo")
    assert outcome is Outcome.OK
    assert lines == ["display zone is now Asia/Tokyo"]
    _, result = run(env, "now")
    assert "Asia/Tokyo" in result[0]


def test_tz_rejects_an_unknown_zone(env: Env) -> None:
    outcome, lines = run(env, ":tz Atlantis")
    assert outcome is Outcome.ERROR
    assert "unknown timezone" in lines[0]
    assert env.zone == NY


def test_fmt_reports_the_current_format(env: Env) -> None:
    assert run(env, ":fmt") == (Outcome.OK, ["format is iso, 24h clock"])


def test_fmt_switches_the_format(env: Env) -> None:
    run(env, ":fmt human")
    _, lines = run(env, "now")
    assert lines[0] == "Sat 2026-05-23 12:15:13 EDT"
    run(env, ":fmt unix")
    _, lines = run(env, "now")
    assert lines[0] == "1779552913"


def test_fmt_rejects_an_unknown_mode(env: Env) -> None:
    outcome, lines = run(env, ":fmt sideways")
    assert outcome is Outcome.ERROR
    assert "unknown setting" in lines[0]
    # The message names both categories, since a bad word could be either.
    assert "formats are" in lines[0]
    assert "clocks are" in lines[0]
    assert env.fmt == "iso"


def test_an_unknown_command_is_an_error(env: Env) -> None:
    outcome, lines = run(env, ":nope")
    assert outcome is Outcome.ERROR
    assert "unknown command ':nope'" in lines[0]


def test_a_leading_colon_literal_is_not_a_command(env: Env) -> None:
    assert run(env, ":12:15") == (Outcome.OK, ["12m15s"])


def test_colour_reaches_results_and_errors(env: Env) -> None:
    from dtcalc.format import ANSI

    assert execute_line("1h + 1h", env, ANSI).lines[0] == "\x1b[32m2h\x1b[0m"
    assert execute_line("now +", env, ANSI).lines[0].startswith("\x1b[31m")


def test_a_note_stays_plain_next_to_a_coloured_result(env: Env) -> None:
    from dtcalc.format import ANSI

    lines = execute_line("2026-03-07T02:30 + 1d", env, ANSI).lines
    assert lines[0].startswith("\x1b[32m")
    assert "\x1b" not in lines[1]


# --------------------------------------------------------------------------
# 11.4  :fmt with a clock modifier
# --------------------------------------------------------------------------


def test_fmt_timeonly(env: Env) -> None:
    run(env, ":fmt timeonly")
    _, lines = run(env, "now")
    assert lines[0] == "12:15:13 EDT"


def test_fmt_timeonly_marks_a_rollover(env: Env) -> None:
    run(env, ":fmt timeonly")
    _, lines = run(env, "now + 20h")
    assert lines[0] == "08:15:13 EDT (+1d)"


def test_fmt_accepts_a_clock_modifier_alongside_the_format(env: Env) -> None:
    outcome, lines = run(env, ":fmt timeonly 12h")
    assert outcome is Outcome.OK
    assert lines == ["format is now timeonly, 12h clock"]
    _, result = run(env, "now")
    assert result[0] == "12:15:13 PM EDT"


def test_fmt_accepts_a_bare_clock_modifier(env: Env) -> None:
    run(env, ":fmt timeonly")
    outcome, lines = run(env, ":fmt 12h")
    assert outcome is Outcome.OK
    assert lines == ["format is now timeonly, 12h clock"]
    _, result = run(env, "now")
    assert result[0] == "12:15:13 PM EDT"


def test_a_bare_clock_modifier_leaves_the_format_alone(env: Env) -> None:
    run(env, ":fmt human")
    run(env, ":fmt 12h")
    _, lines = run(env, "now")
    assert lines[0] == "Sat 2026-05-23 12:15:13 PM EDT"


def test_fmt_reports_both_settings(env: Env) -> None:
    assert run(env, ":fmt") == (Outcome.OK, ["format is iso, 24h clock"])


def test_fmt_rejects_an_unknown_clock(env: Env) -> None:
    outcome, lines = run(env, ":fmt timeonly 13h")
    assert outcome is Outcome.ERROR
    assert "13h" in lines[0]
    # Nothing is applied when any word in the command is bad.
    assert env.fmt == "iso"
    assert env.clock_style == "24h"


def test_switching_back_to_24h(env: Env) -> None:
    run(env, ":fmt timeonly 12h")
    run(env, ":fmt 24h")
    _, lines = run(env, "now")
    assert lines[0] == "12:15:13 EDT"


def test_vars_uses_the_current_format(env: Env) -> None:
    run(env, "a = now")
    run(env, ":fmt timeonly")
    _, lines = run(env, ":vars")
    assert lines == ["a  12:15:13 EDT"]
