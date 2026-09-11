"""Tests for the single error type and its caret rendering."""

import pytest

from dtcalc.errors import DtcalcError


def test_message_only_renders_without_a_caret() -> None:
    err = DtcalcError("something went wrong")
    assert err.render("now + 7h") == "error: something went wrong"


def test_single_character_span() -> None:
    err = DtcalcError("unexpected token", 4, 5)
    assert err.render("now + 7h") == "error: unexpected token\n  now + 7h\n      ^"


def test_multi_character_span_underlines_the_whole_token() -> None:
    err = DtcalcError("unknown zone", 8, 16)
    assert err.render("now in Xanadu!!") == (
        "error: unknown zone\n  now in Xanadu!!\n          ^^^^^^^"
    )


def test_span_at_the_start_of_the_line() -> None:
    err = DtcalcError("bad literal", 0, 3)
    assert err.render("12: + 1h") == "error: bad literal\n  12: + 1h\n  ^^^"


def test_span_at_the_end_of_the_line() -> None:
    err = DtcalcError("trailing operator", 4, 5)
    assert err.render("now +") == "error: trailing operator\n  now +\n      ^"


def test_span_past_the_end_of_the_line_is_clamped() -> None:
    """A parser reporting EOF points one past the last character."""
    err = DtcalcError("unexpected end of input", 5, 6)
    assert err.render("now +") == "error: unexpected end of input\n  now +\n       ^"


def test_zero_width_span_still_shows_one_caret() -> None:
    err = DtcalcError("expected an expression", 5, 5)
    assert err.render("now +") == "error: expected an expression\n  now +\n       ^"


def test_tabs_are_expanded_so_the_caret_stays_aligned() -> None:
    err = DtcalcError("unexpected token", 4, 5)
    rendered = err.render("now\t+\t7h")
    line, caret = rendered.split("\n")[1:]
    assert "\t" not in line
    assert caret.index("^") == line.index("+")


def test_is_an_exception_and_carries_its_message() -> None:
    with pytest.raises(DtcalcError, match="nope"):
        raise DtcalcError("nope", 0, 1)


def test_span_is_optional_but_must_be_complete() -> None:
    with pytest.raises(ValueError):
        DtcalcError("half a span", 3, None)
