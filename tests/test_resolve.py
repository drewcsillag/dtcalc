"""Tests for the colon-literal resolution pass.

Resolution takes the variable environment, because the decision is not always
statically knowable: in ``12:15 + foo`` the literal is a clock reading if
``foo`` is a duration, and a duration if ``foo`` is an instant.  Variables are
eager, so by the time a line is evaluated their types are known.
"""

from __future__ import annotations

import pytest

from dtcalc.ast import sexpr
from dtcalc.errors import DtcalcError
from dtcalc.parser import parse
from dtcalc.resolve import Kind, resolve

EMPTY: dict[str, Kind] = {}


def r(source: str, types: dict[str, Kind] | None = None) -> str:
    return sexpr(resolve(parse(source), types or EMPTY))


# --------------------------------------------------------------------------
# the two readings, decided by context
# --------------------------------------------------------------------------


def test_the_original_request_subtraction_reads_as_a_duration() -> None:
    assert r("2026-05-23T12:15:13 - 12:15") == "(- dt(2026-05-23T12:15:13) 12h15m)"


def test_a_conversion_reads_as_a_clock_time() -> None:
    assert r("12:13 in Tokyo") == "(in tod(12:13:00) Tokyo)"


def test_an_attach_reads_as_a_clock_time() -> None:
    assert r("12:13 @ sf") == "(@ tod(12:13:00) sf)"


def test_a_bare_colon_literal_reads_as_a_clock_time() -> None:
    assert r("12:15") == "tod(12:15:00)"


def test_the_tie_break_prefers_a_clock_time() -> None:
    """Both readings typecheck in `12:15 + 3h`, so the tie-break decides."""
    assert r("12:15 + 3h") == "(+ tod(12:15:00) 3h)"


def test_a_suffix_forces_the_duration_reading() -> None:
    assert r("12:15m + 3h") == "(+ 12m15s 3h)"
    assert r("12:15h + 3h") == "(+ 12h15m 3h)"


def test_a_leading_colon_forces_the_duration_reading() -> None:
    assert r(":12:15 + 3h") == "(+ 12m15s 3h)"
    assert r("::15 + 3h") == "(+ 15s 3h)"


def test_multiplication_forces_the_duration_reading() -> None:
    assert r("12:15 * 2") == "(* 12h15m 2)"
    assert r("2 * 12:15") == "(* 2 12h15m)"
    assert r("12:15 / 3") == "(/ 12h15m 3)"
    assert r("12:15 % 15m") == "(% 12h15m 15m)"


def test_negation_forces_the_duration_reading() -> None:
    assert r("-12:15") == "(neg 12h15m)"


def test_three_field_literals() -> None:
    assert r("1:02:03 in Tokyo") == "(in tod(01:02:03) Tokyo)"
    assert r("now - 1:02:03") == "(- now 1h2m3s)"


def test_fractional_seconds_survive_both_readings() -> None:
    assert r("now - 0:00:01.5") == "(- now 1.5s)"
    assert r("12:15:13.5 in Tokyo") == "(in tod(12:15:13.5) Tokyo)"


# --------------------------------------------------------------------------
# resolution against the environment
# --------------------------------------------------------------------------


def test_a_duration_variable_leaves_the_tie_break_in_place() -> None:
    assert r("12:15 + foo", {"foo": Kind.DURATION}) == "(+ tod(12:15:00) foo)"


def test_an_instant_variable_forces_the_duration_reading() -> None:
    assert r("12:15 + foo", {"foo": Kind.INSTANT}) == "(+ 12h15m foo)"


def test_an_instant_variable_on_the_left_of_a_subtraction() -> None:
    assert r("foo - 12:15", {"foo": Kind.INSTANT}) == "(- foo 12h15m)"


def test_a_duration_variable_on_the_left_of_a_subtraction() -> None:
    assert r("foo - 12:15", {"foo": Kind.DURATION}) == "(- foo 12h15m)"


def test_an_instant_variable_on_the_right_of_a_subtraction() -> None:
    """`12:15 - foo` with foo an instant can only be instant minus instant."""
    assert r("12:15 - foo", {"foo": Kind.INSTANT}) == "(- tod(12:15:00) foo)"


def test_comparison_against_an_instant_forces_a_clock_time() -> None:
    assert r("12:15 < foo", {"foo": Kind.INSTANT}) == "(< tod(12:15:00) foo)"


def test_comparison_against_a_duration_forces_a_duration() -> None:
    assert r("12:15 < foo", {"foo": Kind.DURATION}) == "(< 12h15m foo)"


def test_an_unbound_variable_is_a_clear_error() -> None:
    with pytest.raises(DtcalcError, match="undefined variable 'nope'"):
        resolve(parse("nope + 1h"), EMPTY)


def test_an_unbound_variable_reports_its_position() -> None:
    with pytest.raises(DtcalcError) as excinfo:
        resolve(parse("1h + nope"), EMPTY)
    assert (excinfo.value.start, excinfo.value.end) == (5, 9)


def test_assignment_does_not_need_the_name_to_exist_yet() -> None:
    assert r("foo = 12:15 + 3h") == "(= foo (+ tod(12:15:00) 3h))"


def test_a_variable_may_be_reassigned_from_itself() -> None:
    assert r("foo = foo + 1h", {"foo": Kind.INSTANT}) == "(= foo (+ foo 1h))"


# --------------------------------------------------------------------------
# static type errors resolution can prove
# --------------------------------------------------------------------------


def test_adding_two_points_in_time_is_rejected_before_evaluation() -> None:
    """Wording widened now that a date is also a point in time."""
    for source in ["now + now", "today + tomorrow", "today + now"]:
        with pytest.raises(DtcalcError, match="cannot add two points in time"):
            resolve(parse(source), EMPTY)


def test_converting_a_duration_is_rejected() -> None:
    with pytest.raises(DtcalcError, match="a date or an instant"):
        resolve(parse("5h in Tokyo"), EMPTY)


def test_attaching_a_zone_to_a_duration_is_rejected() -> None:
    with pytest.raises(DtcalcError, match="a date or an instant"):
        resolve(parse("5h @ Tokyo"), EMPTY)


def test_a_forced_duration_cannot_be_converted() -> None:
    """Caught by the operand's kind now, before the colon literal is decided,
    so the message names the duration rather than the literal's form."""
    with pytest.raises(DtcalcError, match="can only convert a date or an instant"):
        resolve(parse(":12:15 in Tokyo"), EMPTY)


def test_negating_an_instant_is_rejected() -> None:
    with pytest.raises(DtcalcError, match="negate"):
        resolve(parse("-now"), EMPTY)


# --------------------------------------------------------------------------
# clock-reading range validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize("source", ["25:00 in Tokyo", "12:60 in Tokyo", "1:02:99 in Tokyo"])
def test_an_impossible_clock_reading_is_rejected(source: str) -> None:
    with pytest.raises(DtcalcError, match="not a time of day"):
        resolve(parse(source), EMPTY)


def test_an_impossible_clock_reading_is_fine_as_a_duration() -> None:
    assert r("now + 25:00") == "(+ now 25h)"


def test_a_two_field_literal_defaults_its_seconds_to_zero() -> None:
    assert r("09:30 in Tokyo") == "(in tod(09:30:00) Tokyo)"


# --------------------------------------------------------------------------
# day expressions and function arguments
# --------------------------------------------------------------------------


def test_a_time_attached_to_a_day_is_always_a_clock_reading() -> None:
    assert r("today 12:13") == "(at today tod(12:13:00))"
    assert r("upcoming friday 09:00") == "(at upcoming(friday) tod(09:00:00))"


def test_a_forced_duration_cannot_narrow_a_day() -> None:
    with pytest.raises(DtcalcError, match="not a time of day"):
        resolve(parse("today 12:15m"), EMPTY)


def test_function_arguments_are_resolved_by_signature() -> None:
    assert r("round(12:15, 15m)") == "(round tod(12:15:00) 15m)"
    assert r("diff(12:13, now)") == "(diff tod(12:13:00) now)"
    assert r("trunc(now, 12:15)") == "(trunc now 12h15m)"


def test_an_unknown_function_is_an_error() -> None:
    with pytest.raises(DtcalcError, match="unknown function"):
        resolve(parse("nope(now)"), EMPTY)


def test_wrong_arity_is_caught_at_resolution() -> None:
    with pytest.raises(DtcalcError, match="argument"):
        resolve(parse("diff(now)"), EMPTY)
    with pytest.raises(DtcalcError, match="argument"):
        resolve(parse("unix(now, now)"), EMPTY)


def test_a_resolved_tree_contains_no_colon_literals() -> None:
    from dtcalc.ast import ColonLit

    def walk(text: str) -> None:
        tree = resolve(parse(text), {"foo": Kind.INSTANT})
        assert "colon(" not in sexpr(tree)
        assert not isinstance(tree, ColonLit)

    for source in ["12:15", "12:15 + foo", "foo - 12:15", "round(12:15, 1h)", "today 12:13"]:
        walk(source)


# --------------------------------------------------------------------------
# 3.2  inference with dates
# --------------------------------------------------------------------------


def test_a_bare_date_literal_is_a_date() -> None:
    assert r("2026-12-24") == "date(2026-12-24)"


def test_a_datetime_literal_is_still_an_instant() -> None:
    assert r("2026-12-24T12:15") == "dt(2026-12-24T12:15)"


@pytest.mark.parametrize(
    "source", ["today", "tomorrow", "yesterday", "upcoming friday", "previous 15th"]
)
def test_the_keyword_dates_resolve_without_complaint(source: str) -> None:
    assert r(source) == sexpr(resolve(parse(source), EMPTY))


def test_a_colon_literal_after_a_date_resolves_to_a_duration() -> None:
    """Unchanged from instants: subtracting from a date wants a duration."""
    assert r("2026-12-24 - 12:15") == "(- date(2026-12-24) 12h15m)"


def test_a_colon_literal_after_at_resolves_to_a_clock_reading() -> None:
    assert r("2026-12-24 @ 12:00") == "(at date(2026-12-24) tod(12:00:00))"


def test_a_date_variable_drives_the_same_inference_as_a_literal() -> None:
    assert r("foo - 12:15", {"foo": Kind.DATE}) == "(- foo 12h15m)"
    assert r("12:15 + foo", {"foo": Kind.DATE}) == "(+ 12h15m foo)"


def test_a_date_may_be_converted_or_have_a_zone_attached() -> None:
    """Reversed from the first design: a zone promotes rather than erroring."""
    assert r("2026-12-24 in Tokyo") == "(in date(2026-12-24) Tokyo)"
    assert r("2026-12-24 @ Tokyo") == "(@ date(2026-12-24) Tokyo)"


@pytest.mark.parametrize(
    ("source", "message"),
    [("-today", "cannot negate a date"), ("-now", "cannot negate an instant")],
)
def test_negating_a_point_in_time_is_rejected_statically(source: str, message: str) -> None:
    """The article is generated, because "a instant" shipped once already."""
    with pytest.raises(DtcalcError, match=message):
        resolve(parse(source), EMPTY)


def test_adding_two_dates_is_rejected_statically() -> None:
    with pytest.raises(DtcalcError, match="cannot add"):
        resolve(parse("today + tomorrow"), EMPTY)


def test_adding_a_date_to_an_instant_is_rejected_statically() -> None:
    with pytest.raises(DtcalcError, match="cannot add"):
        resolve(parse("today + now"), EMPTY)
