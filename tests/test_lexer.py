"""Tests for the lexer.

Three ambiguities get pinned here, because each one would otherwise be
decided by accident:

* hyphens are both date separators and the subtraction operator
* ``m``, ``ms`` and ``mo`` share a prefix, as do ``d`` and ``bd``
* a leading ``:`` starts either a colon literal or a meta-command
"""

from __future__ import annotations

import pytest

from dtcalc.duration import Duration
from dtcalc.errors import DtcalcError
from dtcalc.lexer import ColonLiteral, TokenKind, is_meta_command, tokenize

D = Duration.build
K = TokenKind


def kinds(source: str) -> list[TokenKind]:
    return [token.kind for token in tokenize(source)]


def texts(source: str) -> list[str]:
    return [token.text for token in tokenize(source)]


def only(source: str) -> object:
    (token,) = tokenize(source)
    return token.value


# --------------------------------------------------------------------------
# 3.1  numbers, unit durations, identifiers, operators
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("source", "expected"), [("5", 5.0), ("1.5", 1.5), ("0", 0.0)])
def test_numbers(source: str, expected: float) -> None:
    assert kinds(source) == [K.NUMBER]
    assert only(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("7h", D(h=7)),
        ("5m", D(m=5)),
        ("30s", D(s=30)),
        ("250ms", D(ms=250)),
        ("3w", D(w=3)),
        ("2d", D(d=2)),
        ("6mo", D(mo=6)),
        ("2y", D(y=2)),
        ("3bd", D(bd=3)),
        ("3w2h5m", D(w=3, h=2, m=5)),
        ("1h30m", D(h=1, m=30)),
        ("1.5s", D(s=1.5)),
        ("1y2mo", D(y=1, mo=2)),
        ("1m30s", D(m=1, s=30)),
    ],
)
def test_unit_durations(source: str, expected: Duration) -> None:
    assert kinds(source) == [K.DURATION]
    assert only(source) == expected


def test_longest_match_distinguishes_m_ms_and_mo() -> None:
    assert only("3m") == D(m=3)
    assert only("3ms") == D(ms=3)
    assert only("3mo") == D(mo=3)


def test_longest_match_distinguishes_d_and_bd() -> None:
    assert only("3d") == D(d=3)
    assert only("3bd") == D(bd=3)


@pytest.mark.parametrize("source", ["foo", "bar_1", "_x", "myVar"])
def test_identifiers(source: str) -> None:
    assert kinds(source) == [K.IDENT]
    assert texts(source) == [source]


@pytest.mark.parametrize("source", ["s", "m", "h", "d", "w", "y", "mo", "ms", "bd"])
def test_bare_unit_names_are_not_identifiers(source: str) -> None:
    with pytest.raises(DtcalcError, match="unit"):
        tokenize(source)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("+", [K.PLUS]),
        ("-", [K.MINUS]),
        ("*", [K.STAR]),
        ("/", [K.SLASH]),
        ("%", [K.PERCENT]),
        ("@", [K.AT]),
        ("=", [K.ASSIGN]),
        ("==", [K.EQ]),
        ("!=", [K.NE]),
        ("<", [K.LT]),
        ("<=", [K.LE]),
        (">", [K.GT]),
        (">=", [K.GE]),
        ("(", [K.LPAREN]),
        (")", [K.RPAREN]),
        (",", [K.COMMA]),
    ],
)
def test_operators(source: str, expected: list[TokenKind]) -> None:
    assert kinds(source) == expected


def test_whitespace_is_not_significant() -> None:
    assert kinds("  now   +  7h ") == kinds("now+7h")


# --------------------------------------------------------------------------
# 3.1a  the ambiguity rules
# --------------------------------------------------------------------------


def test_a_date_is_matched_greedily_so_hyphens_do_not_confuse_subtraction() -> None:
    assert kinds("2026-05-23 - 5h") == [K.DATE, K.MINUS, K.DURATION]


def test_a_date_followed_immediately_by_a_minus_is_still_subtraction() -> None:
    assert kinds("2026-05-23-5h") == [K.DATE, K.MINUS, K.DURATION]
    assert texts("2026-05-23-5h") == ["2026-05-23", "-", "5h"]


def test_an_identifier_and_a_duration_split_on_the_minus() -> None:
    assert kinds("foo-5h") == [K.IDENT, K.MINUS, K.DURATION]
    assert texts("foo-5h") == ["foo", "-", "5h"]


def test_a_trailing_offset_needs_a_colon_so_it_cannot_swallow_a_subtraction() -> None:
    assert kinds("2026-05-23T12:15:13-07:00") == [K.DATETIME]
    assert kinds("2026-05-23T12:15:13-5h") == [K.DATETIME, K.MINUS, K.DURATION]


def test_a_duration_cannot_run_into_an_identifier() -> None:
    with pytest.raises(DtcalcError):
        tokenize("5hfoo")


# --------------------------------------------------------------------------
# 3.2  colon literals and the meta-command boundary
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "fields", "leading", "forced"),
    [
        ("12:15", (12.0, 15.0), "h", False),
        ("1:02:03", (1.0, 2.0, 3.0), "h", False),
        ("12:15:13.5", (12.0, 15.0, 13.5), "h", False),
        ("12:15h", (12.0, 15.0), "h", True),
        ("1:02:03h", (1.0, 2.0, 3.0), "h", True),
        ("12:15m", (12.0, 15.0), "m", True),
        (":12:15", (None, 12.0, 15.0), "h", True),
        ("::15", (None, None, 15.0), "h", True),
        (":12", (None, 12.0), "h", True),
    ],
)
def test_colon_literals(
    source: str, fields: tuple[float | None, ...], leading: str, forced: bool
) -> None:
    assert kinds(source) == [K.COLON_LITERAL]
    literal = only(source)
    assert isinstance(literal, ColonLiteral)
    assert literal.fields == fields
    assert literal.leading == leading
    assert literal.forced_duration is forced


@pytest.mark.parametrize("source", ["12:15s", "12:15d", "12:15ms", "12:15y"])
def test_only_h_and_m_may_be_a_colon_literal_suffix(source: str) -> None:
    with pytest.raises(DtcalcError, match="leading unit"):
        tokenize(source)


def test_a_minute_leading_colon_literal_cannot_have_three_fields() -> None:
    with pytest.raises(DtcalcError, match="too many"):
        tokenize("1:02:03m")


def test_a_colon_literal_cannot_have_four_fields() -> None:
    with pytest.raises(DtcalcError, match="too many"):
        tokenize("1:2:3:4")


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (":help", True),
        (":q", True),
        (":tz Tokyo", True),
        (":fmt iso", True),
        ("  :help", True),
        (":12:15", False),
        ("::15", False),
        (":12:15 + 3h", False),
        ("now + 7h", False),
        (":", False),
        ("", False),
    ],
)
def test_meta_command_detection(line: str, expected: bool) -> None:
    """A leading colon before a letter is a command; before a digit or colon it is a value."""
    assert is_meta_command(line) is expected


def test_a_leading_colon_literal_still_lexes_as_an_expression() -> None:
    assert kinds(":12:15 + 3h") == [K.COLON_LITERAL, K.PLUS, K.DURATION]


# --------------------------------------------------------------------------
# 3.3  ISO literals and keywords
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "kind"),
    [
        ("2026-05-23T12:15:13", K.DATETIME),
        ("2026-05-23T12:15", K.DATETIME),
        ("2026-05-23 12:15:13", K.DATETIME),
        ("2026-05-23T12:15:13.25", K.DATETIME),
        ("2026-05-23T12:15:13Z", K.DATETIME),
        ("2026-05-23T12:15:13+05:30", K.DATETIME),
        ("2026-05-23", K.DATE),
    ],
)
def test_iso_literals(source: str, kind: TokenKind) -> None:
    assert kinds(source) == [kind]


def test_datetime_literal_values() -> None:
    from dtcalc.lexer import DateTimeLiteral

    literal = only("2026-05-23T12:15:13-07:00")
    assert isinstance(literal, DateTimeLiteral)
    assert (literal.year, literal.month, literal.day) == (2026, 5, 23)
    assert (literal.hour, literal.minute, literal.second) == (12, 15, 13)
    assert literal.offset_minutes == -7 * 60


def test_date_only_literal_has_no_time() -> None:
    from dtcalc.lexer import DateTimeLiteral

    literal = only("2026-05-23")
    assert isinstance(literal, DateTimeLiteral)
    assert literal.has_time is False


@pytest.mark.parametrize("source", ["2026-13-01", "2026-02-30", "2026-05-23T25:00"])
def test_impossible_dates_and_times_are_rejected(source: str) -> None:
    with pytest.raises(DtcalcError):
        tokenize(source)


@pytest.mark.parametrize(
    ("source", "kind"),
    [
        ("now", K.NOW),
        ("today", K.TODAY),
        ("tomorrow", K.TOMORROW),
        ("yesterday", K.YESTERDAY),
        ("in", K.IN),
        ("upcoming", K.UPCOMING),
        ("previous", K.PREVIOUS),
    ],
)
def test_keywords(source: str, kind: TokenKind) -> None:
    assert kinds(source) == [kind]


def test_keywords_are_case_insensitive() -> None:
    assert kinds("NOW") == kinds("Now") == [K.NOW]


@pytest.mark.parametrize(
    ("source", "weekday"),
    [
        ("monday", 0),
        ("mon", 0),
        ("friday", 4),
        ("fri", 4),
        ("FRIDAY", 4),
        ("sunday", 6),
        ("sun", 6),
    ],
)
def test_weekday_names(source: str, weekday: int) -> None:
    assert kinds(source) == [K.WEEKDAY]
    assert only(source) == weekday


@pytest.mark.parametrize(
    ("source", "day"),
    [("1st", 1), ("2nd", 2), ("3rd", 3), ("15th", 15), ("21st", 21), ("31st", 31)],
)
def test_ordinal_day_of_month(source: str, day: int) -> None:
    assert kinds(source) == [K.ORDINAL]
    assert only(source) == day


def test_an_ordinal_outside_the_month_is_rejected() -> None:
    with pytest.raises(DtcalcError, match="day of the month"):
        tokenize("32nd")


def test_an_ordinal_beats_the_seconds_unit_by_being_longer() -> None:
    assert kinds("1st") == [K.ORDINAL]
    assert kinds("1s") == [K.DURATION]


def test_a_realistic_expression() -> None:
    assert kinds("bar = foo + 3w2h5m in Tokyo") == [
        K.IDENT,
        K.ASSIGN,
        K.IDENT,
        K.PLUS,
        K.DURATION,
        K.IN,
        K.IDENT,
    ]


def test_a_zone_path_lexes_as_parts_for_the_parser_to_rejoin() -> None:
    assert kinds("now in America/New_York") == [K.NOW, K.IN, K.IDENT, K.SLASH, K.IDENT]


# --------------------------------------------------------------------------
# 3.4  error positions
# --------------------------------------------------------------------------


def test_an_unknown_character_reports_its_position() -> None:
    with pytest.raises(DtcalcError) as excinfo:
        tokenize("now + 7h $")
    assert (excinfo.value.start, excinfo.value.end) == (9, 10)


def test_a_bad_duration_reports_the_whole_literal() -> None:
    with pytest.raises(DtcalcError) as excinfo:
        tokenize("now + 5hfoo")
    assert excinfo.value.start == 6


def test_the_caret_lands_under_the_offending_token() -> None:
    line = "now + 7h $"
    with pytest.raises(DtcalcError) as excinfo:
        tokenize(line)
    rendered = excinfo.value.render(line)
    caret_line = rendered.split("\n")[2]
    assert caret_line.strip() == "^"
    assert caret_line.index("^") == rendered.split("\n")[1].index("$")


def test_token_spans_cover_the_source() -> None:
    tokens = tokenize("foo-5h")
    assert [(t.start, t.end) for t in tokens] == [(0, 3), (3, 4), (4, 6)]


def test_a_hash_starts_a_comment_that_runs_to_the_end_of_the_line() -> None:
    assert kinds("now + 7h  # seven hours from now") == [K.NOW, K.PLUS, K.DURATION]


def test_a_comment_only_line_yields_no_tokens() -> None:
    assert tokenize("# just a note") == []
    assert tokenize("") == []


# --------------------------------------------------------------------------
# 11.2  am/pm clock literals
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("4p", (16, 0, 0, 0)),
        ("4a", (4, 0, 0, 0)),
        ("4pm", (16, 0, 0, 0)),
        ("4am", (4, 0, 0, 0)),
        ("4PM", (16, 0, 0, 0)),
        ("4:30p", (16, 30, 0, 0)),
        ("4:30pm", (16, 30, 0, 0)),
        ("11:59:59p", (23, 59, 59, 0)),
        ("4:30:15.5am", (4, 30, 15, 500_000)),
        ("1p", (13, 0, 0, 0)),
        ("11a", (11, 0, 0, 0)),
        # The two everyone gets wrong.
        ("12a", (0, 0, 0, 0)),
        ("12p", (12, 0, 0, 0)),
        ("12:30a", (0, 30, 0, 0)),
        ("12:30p", (12, 30, 0, 0)),
    ],
)
def test_meridiem_clock_literals(source: str, expected: tuple[int, int, int, int]) -> None:
    from dtcalc.lexer import ClockLiteral

    assert kinds(source) == [K.CLOCK]
    literal = only(source)
    assert isinstance(literal, ClockLiteral)
    assert (literal.hour, literal.minute, literal.second, literal.microsecond) == expected


@pytest.mark.parametrize("source", ["0p", "13p", "0a", "24a", "99pm"])
def test_a_meridiem_hour_outside_one_to_twelve_is_rejected(source: str) -> None:
    with pytest.raises(DtcalcError, match="12-hour clock"):
        tokenize(source)


@pytest.mark.parametrize("source", ["4:60p", "4:30:60a"])
def test_an_impossible_meridiem_time_is_rejected(source: str) -> None:
    with pytest.raises(DtcalcError, match="not a time of day"):
        tokenize(source)


def test_a_meridiem_literal_does_not_swallow_a_following_word() -> None:
    with pytest.raises(DtcalcError):
        tokenize("4pmx")


def test_meridiem_literals_coexist_with_the_other_digit_forms() -> None:
    assert kinds("4p") == [K.CLOCK]
    assert kinds("4:30") == [K.COLON_LITERAL]
    assert kinds("4h") == [K.DURATION]
    assert kinds("4th") == [K.ORDINAL]
    assert kinds("4") == [K.NUMBER]
    assert kinds("4ms") == [K.DURATION]


def test_a_meridiem_literal_in_an_expression() -> None:
    assert kinds("foo @ 4p") == [K.IDENT, K.AT, K.CLOCK]
    assert kinds("4p + 1h") == [K.CLOCK, K.PLUS, K.DURATION]


def test_an_identifier_named_a_or_p_is_still_usable() -> None:
    """`a` and `p` are not units, so they remain ordinary variable names."""
    assert kinds("a = 4p") == [K.IDENT, K.ASSIGN, K.CLOCK]
    assert kinds("p + a") == [K.IDENT, K.PLUS, K.IDENT]
