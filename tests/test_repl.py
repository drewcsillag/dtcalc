"""Tests for the REPL's pure parts: the completer and the prompt escaping.

The readline wiring itself needs a terminal and is covered by
``test_interactive.py``.
"""

from __future__ import annotations

import pytest

from dtcalc.clock import FixedClock
from dtcalc.env import Env
from dtcalc.format import ANSI, PLAIN
from dtcalc.repl import completions, readline_prompt

from .support import NY, TEST_NOW


@pytest.fixture
def env() -> Env:
    from dtcalc.duration import Duration

    env = Env(clock=FixedClock(TEST_NOW), zone=NY)
    env.variables["foo"] = Duration.build(h=1)
    env.variables["fudge"] = Duration.build(m=5)
    env.variables["bar"] = Duration.build(m=2)
    return env


def at_end(line: str) -> int:
    return len(line)


# --------------------------------------------------------------------------
# names
# --------------------------------------------------------------------------


def test_variables_complete(env: Env) -> None:
    assert completions("fo", at_end("fo"), env) == ["foo"]


def test_a_shared_prefix_offers_every_matching_name(env: Env) -> None:
    candidates = completions("f", at_end("f"), env)
    assert {"foo", "fudge"} <= set(candidates)
    assert "friday" in candidates  # keywords are in scope too
    assert "bar" not in candidates


def test_functions_complete(env: Env) -> None:
    assert completions("rou", at_end("rou"), env) == ["round"]
    assert "epoch" in completions("ep", at_end("ep"), env)
    assert "epochms" in completions("ep", at_end("ep"), env)


def test_keywords_complete(env: Env) -> None:
    assert completions("tod", at_end("tod"), env) == ["today"]
    assert completions("upc", at_end("upc"), env) == ["upcoming"]


def test_completion_looks_only_at_the_word_under_the_cursor(env: Env) -> None:
    line = "1h + fo"
    assert completions(line, at_end(line), env) == ["foo"]


def test_an_empty_prefix_offers_nothing(env: Env) -> None:
    """Dumping every name on an empty line is noise, not help."""
    assert completions("", 0, env) == []
    assert completions("1h + ", at_end("1h + "), env) == []


def test_an_unmatched_prefix_offers_nothing(env: Env) -> None:
    assert completions("zzz", at_end("zzz"), env) == []


def test_results_are_sorted_and_unique(env: Env) -> None:
    candidates = completions("e", at_end("e"), env)
    assert candidates == sorted(set(candidates))


# --------------------------------------------------------------------------
# zones
# --------------------------------------------------------------------------


def test_after_in_the_candidates_are_zones(env: Env) -> None:
    line = "now in Tok"
    assert completions(line, at_end(line), env) == ["Tokyo"]


def test_a_matching_alias_is_offered_alone(env: Env) -> None:
    """`Tokyo` and `Asia/Tokyo` share no common prefix, so offering both
    would complete nothing at all.  The curated alias wins."""
    line = "now in Toky"
    assert completions(line, at_end(line), env) == ["Tokyo"]


def test_the_full_iana_list_is_there_when_no_alias_matches(env: Env) -> None:
    line = "now in Reykjav"
    assert completions(line, at_end(line), env) == ["Atlantic/Reykjavik"]


def test_an_iana_prefix_completes(env: Env) -> None:
    line = "now in Asia/Tok"
    assert completions(line, at_end(line), env) == ["Asia/Tokyo"]


def test_after_at_the_candidates_are_zones(env: Env) -> None:
    line = "12:13 @ san"
    assert "SanFrancisco" in completions(line, at_end(line), env)


def test_a_zone_path_completes_on_its_last_segment(env: Env) -> None:
    line = "now in New_Yo"
    assert "America/New_York" in completions(line, at_end(line), env)


def test_a_partial_zone_path_completes(env: Env) -> None:
    line = "now in America/New_"
    assert "America/New_York" in completions(line, at_end(line), env)


def test_variables_are_not_offered_where_a_zone_belongs(env: Env) -> None:
    line = "now in fo"
    assert "foo" not in completions(line, at_end(line), env)


def test_zone_completion_after_in_does_not_leak_into_later_words(env: Env) -> None:
    line = "now in Tokyo + fo"
    assert completions(line, at_end(line), env) == ["foo"]


# --------------------------------------------------------------------------
# meta-commands
# --------------------------------------------------------------------------


def test_meta_commands_complete(env: Env) -> None:
    assert completions(":f", at_end(":f"), env) == [":fmt"]
    assert ":help" in completions(":h", at_end(":h"), env)


def test_the_tz_command_completes_zones(env: Env) -> None:
    line = ":tz Tok"
    assert "Tokyo" in completions(line, at_end(line), env)


def test_the_fmt_command_completes_its_modes(env: Env) -> None:
    line = ":fmt hu"
    assert completions(line, at_end(line), env) == ["human"]


# --------------------------------------------------------------------------
# prompt escaping
# --------------------------------------------------------------------------


def test_gnu_readline_gets_its_escape_codes_marked_as_zero_width() -> None:
    """Without the \\001/\\002 markers GNU readline miscounts the line width
    and editing a long line corrupts the display."""
    prompt = readline_prompt("dtcalc> ", ANSI, supports_marks=True)
    assert prompt.startswith("\001\x1b[36m\002")
    assert prompt.endswith("\001\x1b[0m\002")
    assert "dtcalc> " in prompt


def test_libedit_gets_an_uncoloured_prompt() -> None:
    """Under libedit there is no form that both colours and counts correctly.

    Raw codes get counted, so Ctrl-A on a wrapped line lands nine columns
    adrift; the marker form is printed literally.  Plain text is the only
    option that leaves the cursor where it belongs.
    """
    prompt = readline_prompt("dtcalc> ", ANSI, supports_marks=False)
    assert prompt == "dtcalc> "
    assert "\x1b" not in prompt


@pytest.mark.parametrize("supports_marks", [True, False])
def test_a_plain_prompt_is_left_alone(supports_marks: bool) -> None:
    assert readline_prompt("dtcalc> ", PLAIN, supports_marks=supports_marks) == "dtcalc> "
