"""Tests for the command-line surface.

Grows alongside cli.py: the debug dumps land first, the evaluation modes
follow.
"""

from __future__ import annotations

import pytest

from dtcalc.cli import main


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert "dtcalc" in capsys.readouterr().out


def test_dump_tokens_lists_every_token(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--dump-tokens", "foo - 5h"]) == 0
    out = capsys.readouterr().out
    assert "IDENT" in out
    assert "MINUS" in out
    assert "DURATION" in out


def test_dump_tokens_reports_a_lexer_error_with_a_caret(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--dump-tokens", "now + 7h $"]) == 1
    err = capsys.readouterr().err
    assert "unexpected character" in err
    assert "^" in err


def test_dump_ast_shows_both_stages(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--dump-ast", "2026-05-23T12:15:13 - 12:15"]) == 0
    out = capsys.readouterr().out
    assert "parsed:   (- dt(2026-05-23T12:15:13) colon(12:15))" in out
    assert "resolved: (- dt(2026-05-23T12:15:13) 12h15m)" in out


def test_dump_ast_shows_the_tie_break(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--dump-ast", "12:15 + 3h"]) == 0
    assert "resolved: (+ tod(12:15:00) 3h)" in capsys.readouterr().out


def test_dump_ast_reports_a_parse_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--dump-ast", "now +"]) == 1
    assert "^" in capsys.readouterr().err


# --------------------------------------------------------------------------
# 5.2a  one-shot and pipe modes
# --------------------------------------------------------------------------

FROZEN = {"DTCALC_NOW": "2026-05-23T12:15:13", "DTCALC_TZ": "America/New_York"}


@pytest.fixture(autouse=True)
def _frozen_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every CLI test runs with a fixed clock and display zone."""
    for key, value in FROZEN.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("NO_COLOR", "1")


def test_one_shot_evaluates_a_single_expression(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["now + 7h"]) == 0
    assert capsys.readouterr().out == "2026-05-23T19:15:13-04:00  America/New_York\n"


def test_one_shot_reports_the_original_requests_examples(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["2026-05-23T12:15:13 - 12:15"]) == 0
    assert capsys.readouterr().out.startswith("2026-05-23T00:00:13")


def test_one_shot_exits_non_zero_on_an_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["now +"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "^" in captured.err


def test_pipe_mode_evaluates_each_line(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _feed(monkeypatch, "foo = now\nfoo + 5h\n")
    assert main([]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines == [
        "2026-05-23T12:15:13-04:00  America/New_York",
        "2026-05-23T17:15:13-04:00  America/New_York",
    ]


def test_pipe_mode_keeps_going_after_an_error_but_still_fails(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _feed(monkeypatch, "1h + 1h\nnow +\n2h + 2h\n")
    assert main([]) == 1
    captured = capsys.readouterr()
    assert captured.out.splitlines() == ["2h", "4h"]
    assert "^" in captured.err


def test_pipe_mode_ignores_blank_and_comment_lines(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _feed(monkeypatch, "\n# a note\n1h + 1h\n   \n")
    assert main([]) == 0
    assert capsys.readouterr().out.splitlines() == ["2h"]


def test_transcript_mode_echoes_the_input(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _feed(monkeypatch, "1h + 1h\n")
    assert main(["--transcript"]) == 0
    assert capsys.readouterr().out == "dtcalc> 1h + 1h\n2h\n"


def test_transcript_mode_puts_errors_in_the_transcript(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _feed(monkeypatch, "now +\n")
    assert main(["--transcript"]) == 1
    captured = capsys.readouterr()
    assert "^" in captured.out
    assert captured.err == ""


def test_an_unknown_flag_is_rejected() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--nope"])
    assert excinfo.value.code != 0


# --------------------------------------------------------------------------
# 5.4a  deterministic clock and zone
# --------------------------------------------------------------------------


def test_dtcalc_now_freezes_the_clock(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["now"]) == 0
    assert capsys.readouterr().out.startswith("2026-05-23T12:15:13")


def test_dtcalc_now_accepts_an_explicit_offset(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DTCALC_NOW", "2026-05-23T16:15:13+00:00")
    assert main(["now"]) == 0
    assert capsys.readouterr().out.startswith("2026-05-23T12:15:13")


def test_dtcalc_tz_sets_the_display_zone(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DTCALC_TZ", "Asia/Tokyo")
    assert main(["now"]) == 0
    assert "Asia/Tokyo" in capsys.readouterr().out


def test_a_bad_dtcalc_now_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    import os

    os.environ["DTCALC_NOW"] = "not a time"
    assert main(["now"]) == 1
    assert "DTCALC_NOW" in capsys.readouterr().err


def test_a_note_is_printed_alongside_the_result(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["2026-03-07T02:30 + 1d"]) == 0
    out = capsys.readouterr().out
    assert "2026-03-08T03:30:00" in out
    assert "does not exist" in out


def _feed(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    """Replace stdin with ``text`` and make it look like a pipe."""
    import io

    class _Pipe(io.StringIO):
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr("sys.stdin", _Pipe(text))


# --------------------------------------------------------------------------
# 6.3  the --tz flag
# --------------------------------------------------------------------------


def test_tz_flag_sets_the_working_zone(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--tz", "Asia/Tokyo", "now"]) == 0
    assert "Asia/Tokyo" in capsys.readouterr().out


def test_tz_flag_accepts_an_alias(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--tz", "sf", "now"]) == 0
    assert "America/Los_Angeles" in capsys.readouterr().out


def test_tz_flag_beats_the_environment_variable(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Precedence: flag, then DTCALC_TZ, then the detected local zone."""
    monkeypatch.setenv("DTCALC_TZ", "America/New_York")
    assert main(["--tz", "UTC", "now"]) == 0
    assert "UTC" in capsys.readouterr().out


def test_tz_flag_governs_the_arithmetic_not_only_the_rendering(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The point of the rename: `today` differs by zone at this hour."""
    monkeypatch.setenv("DTCALC_NOW", "2026-05-24T02:15:00+00:00")
    assert main(["--tz", "America/New_York", "today"]) == 0
    assert capsys.readouterr().out.strip() == "2026-05-23"
    assert main(["--tz", "UTC", "today"]) == 0
    assert capsys.readouterr().out.strip() == "2026-05-24"


def test_a_bad_tz_flag_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--tz", "Atlantis", "now"]) == 1
    assert "Atlantis" in capsys.readouterr().err
