"""Tests for the parser: AST shape, precedence, and error positions.

The parser does not decide what a colon literal means — it records one as an
unresolved node and :mod:`dtcalc.resolve` settles it later, with the variable
environment in hand.
"""

from __future__ import annotations

import pytest

from dtcalc.ast import sexpr
from dtcalc.errors import DtcalcError
from dtcalc.parser import parse


def s(source: str) -> str:
    return sexpr(parse(source))


# --------------------------------------------------------------------------
# 4.1  shape and precedence
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("5", "5"),
        ("7h", "7h"),
        ("now", "now"),
        ("today", "today"),
        ("tomorrow", "tomorrow"),
        ("yesterday", "yesterday"),
        ("foo", "foo"),
        ("2026-05-23", "date(2026-05-23)"),
        ("2026-05-23T12:15:13", "dt(2026-05-23T12:15:13)"),
        ("12:15", "colon(12:15)"),
        ("upcoming friday", "upcoming(friday)"),
        ("previous mon", "previous(monday)"),
        ("upcoming 15th", "upcoming(15th)"),
        ("previous 1st", "previous(1st)"),
    ],
)
def test_primaries(source: str, expected: str) -> None:
    assert s(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("now + 7h", "(+ now 7h)"),
        ("foo - 5h", "(- foo 5h)"),
        ("foo-5h", "(- foo 5h)"),
        ("3h * 5", "(* 3h 5)"),
        ("5 * 3h", "(* 5 3h)"),
        ("1d / 4", "(/ 1d 4)"),
        ("97m % 15m", "(% 1h37m 15m)"),
        ("-5h", "(neg 5h)"),
        ("+5h", "5h"),
        ("bar = foo + 5h", "(= bar (+ foo 5h))"),
    ],
)
def test_operators(source: str, expected: str) -> None:
    assert s(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # * binds tighter than +
        ("1h + 2h * 3", "(+ 1h (* 2h 3))"),
        ("2h * 3 + 1h", "(+ (* 2h 3) 1h)"),
        # + and - are left associative
        ("1h + 2h + 3h", "(+ (+ 1h 2h) 3h)"),
        ("1h - 2h - 3h", "(- (- 1h 2h) 3h)"),
        ("8h / 2 / 2", "(/ (/ 8h 2) 2)"),
        # @ binds tightest of all
        ("12:13 @ sf + 2h", "(+ (@ colon(12:13) sf) 2h)"),
        ("12:13 @ sf * 2", "(* (@ colon(12:13) sf) 2)"),
        # in binds loosest
        ("now + 1d in Tokyo", "(in (+ now 1d) Tokyo)"),
        ("12:13 @ sf + 2h in Tokyo", "(in (+ (@ colon(12:13) sf) 2h) Tokyo)"),
        # comparisons sit between arithmetic and in
        ("now + 1h < foo", "(< (+ now 1h) foo)"),
        # parens override everything
        ("(1h + 2h) * 3", "(* (+ 1h 2h) 3)"),
        ("(now + 1d) in Tokyo", "(in (+ now 1d) Tokyo)"),
    ],
)
def test_precedence(source: str, expected: str) -> None:
    assert s(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("now in Tokyo", "(in now Tokyo)"),
        ("now in America/New_York", "(in now America/New_York)"),
        ("12:13 @ America/Los_Angeles", "(@ colon(12:13) America/Los_Angeles)"),
        ("now in utc", "(in now utc)"),
    ],
)
def test_zone_names(source: str, expected: str) -> None:
    assert s(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("today 12:13", "(at today colon(12:13))"),
        ("tomorrow 09:00", "(at tomorrow colon(09:00))"),
        ("upcoming friday 09:00", "(at upcoming(friday) colon(09:00))"),
        ("previous 15th 17:30", "(at previous(15th) colon(17:30))"),
    ],
)
def test_a_day_followed_by_a_time_of_day(source: str, expected: str) -> None:
    assert s(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("min(foo, bar)", "(min foo bar)"),
        ("max(now)", "(max now)"),
        ("round(now, 15m)", "(round now 15m)"),
        ("trunc(now, 1h)", "(trunc now 1h)"),
        ("ceil(now, 1d)", "(ceil now 1d)"),
        ("diff(foo, bar)", "(diff foo bar)"),
        ("epoch(1789073107)", "(epoch 1789073107)"),
        ("epochms(1789073107000)", "(epochms 1789073107000)"),
        ("unix(now)", "(unix now)"),
        ("round(now + 1h, 15m)", "(round (+ now 1h) 15m)"),
    ],
)
def test_function_calls(source: str, expected: str) -> None:
    assert s(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a < b", "(< a b)"),
        ("a <= b", "(<= a b)"),
        ("a > b", "(> a b)"),
        ("a >= b", "(>= a b)"),
        ("a == b", "(== a b)"),
        ("a != b", "(!= a b)"),
    ],
)
def test_comparisons(source: str, expected: str) -> None:
    assert s(source) == expected


def test_comparisons_do_not_chain() -> None:
    with pytest.raises(DtcalcError, match="chain"):
        parse("a < b < c")


def test_assignment_does_not_chain() -> None:
    with pytest.raises(DtcalcError):
        parse("a = b = c")


def test_an_empty_source_is_an_error() -> None:
    with pytest.raises(DtcalcError, match="nothing to evaluate"):
        parse("")


# --------------------------------------------------------------------------
# 4.3  parse errors
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "fragment"),
    [
        ("now +", "expected"),
        ("(now + 1h", "closing"),
        ("now + 1h)", "unexpected"),
        ("min(", "expected"),
        ("min(now,", "expected"),
        ("now in", "timezone"),
        ("12:13 @", "timezone"),
        ("now in 5", "timezone"),
        ("* 5h", "unexpected"),
        ("round now, 15m)", "unexpected"),
    ],
)
def test_parse_errors(source: str, fragment: str) -> None:
    with pytest.raises(DtcalcError, match=fragment):
        parse(source)


def test_a_trailing_operator_points_past_the_end() -> None:
    source = "now +"
    with pytest.raises(DtcalcError) as excinfo:
        parse(source)
    assert excinfo.value.start == len(source)


def test_an_unexpected_token_points_at_itself() -> None:
    source = "now + 1h )"
    with pytest.raises(DtcalcError) as excinfo:
        parse(source)
    assert (excinfo.value.start, excinfo.value.end) == (9, 10)


def test_the_caret_marks_the_unclosed_paren_position() -> None:
    source = "(now + 1h"
    with pytest.raises(DtcalcError) as excinfo:
        parse(source)
    rendered = excinfo.value.render(source)
    assert "^" in rendered.split("\n")[2]


@pytest.mark.parametrize("keyword", ["now", "today", "tomorrow", "friday", "upcoming"])
def test_a_keyword_on_the_left_of_an_assignment_says_why(keyword: str) -> None:
    with pytest.raises(DtcalcError, match="keyword, so it cannot be a variable name"):
        parse(f"{keyword} = 3h")


# --------------------------------------------------------------------------
# 11.3  `expr @ <time>`
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("foo @ 16:00", "(at foo colon(16:00))"),
        ("foo @ 4p", "(at foo tod(16:00:00))"),
        ("foo @ 4:30am", "(at foo tod(04:30:00))"),
        ("now @ 9:15", "(at now colon(9:15))"),
        ("(now + 1d) @ 17:00", "(at (+ now 1d) colon(17:00))"),
        ("upcoming friday @ 4p", "(at upcoming(friday) tod(16:00:00))"),
    ],
)
def test_at_a_time_of_day_keeps_the_date(source: str, expected: str) -> None:
    assert s(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("12:13 @ sf", "(@ colon(12:13) sf)"),
        ("now @ America/New_York", "(@ now America/New_York)"),
    ],
)
def test_at_a_zone_still_attaches_a_zone(source: str, expected: str) -> None:
    """A zone name can never start with a digit, so the two forms never collide."""
    assert s(source) == expected


def test_a_bare_meridiem_literal_is_a_clock_reading() -> None:
    assert s("4p") == "tod(16:00:00)"
    assert s("4p + 1h") == "(+ tod(16:00:00) 1h)"


def test_at_binds_tighter_than_arithmetic() -> None:
    assert s("foo @ 4p + 1h") == "(+ (at foo tod(16:00:00)) 1h)"


def test_at_composes_with_a_conversion() -> None:
    assert s("foo @ 4p in Tokyo") == "(in (at foo tod(16:00:00)) Tokyo)"


def test_at_needs_a_zone_or_a_time() -> None:
    with pytest.raises(DtcalcError, match="timezone name or a time of day"):
        parse("now @ 5h")
    with pytest.raises(DtcalcError, match="timezone name or a time of day"):
        parse("now @")
