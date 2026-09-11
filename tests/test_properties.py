"""Property tests.

These target the parts where a table of examples is least likely to be
complete: the colon-literal forms, which have two explicit spellings and an
elidable leading field, and duration round-tripping, where the formatter and
the lexer have to agree about every unit boundary.
"""

from __future__ import annotations

from hypothesis import assume, given
from hypothesis import strategies as st

from dtcalc.clock import FixedClock
from dtcalc.duration import Duration
from dtcalc.env import Env
from dtcalc.evaluator import evaluate_line
from dtcalc.instant import Instant
from dtcalc.lexer import tokenize

from .support import NY, TEST_NOW

D = Duration.build

MAX_MILLIS = 10**12
MAX_DAYS = 10_000
MAX_MONTHS = 10_000


def fresh_env() -> Env:
    return Env(clock=FixedClock(TEST_NOW), zone=NY)


def evaluate(source: str) -> object:
    return evaluate_line(source, fresh_env())


@st.composite
def same_sign_durations(draw: st.DrawFn) -> Duration:
    """Durations whose non-zero ladders agree in sign.

    Mixed signs are excluded because they format as two space-separated
    groups (``1d -1h30m``), which is a readable rendering of one value but
    not a single token — round-tripping those is a different property, tested
    separately below.
    """
    sign = draw(st.sampled_from([1, -1]))
    millis = draw(st.integers(min_value=0, max_value=MAX_MILLIS))
    if draw(st.booleans()):
        # Business days occupy their own ladder and cannot carry calendar
        # parts, so this branch keeps the invariant.
        bdays = draw(st.integers(min_value=0, max_value=MAX_DAYS))
        assume(bdays or millis)
        return Duration(bdays=sign * bdays, millis=sign * millis)
    days = draw(st.integers(min_value=0, max_value=MAX_DAYS))
    months = draw(st.integers(min_value=0, max_value=MAX_MONTHS))
    assume(days or months or millis)
    return Duration(months=sign * months, days=sign * days, millis=sign * millis)


@st.composite
def exact_durations(draw: st.DrawFn) -> Duration:
    return Duration(millis=draw(st.integers(min_value=-MAX_MILLIS, max_value=MAX_MILLIS)))


# --------------------------------------------------------------------------
# formatting round-trips
# --------------------------------------------------------------------------


@given(same_sign_durations())
def test_a_formatted_duration_parses_back_to_itself(duration: Duration) -> None:
    assert evaluate(str(duration)) == duration


@given(same_sign_durations())
def test_a_formatted_duration_is_a_single_token(duration: Duration) -> None:
    """Apart from a leading minus, which the evaluator applies."""
    text = str(duration).removeprefix("-")
    assert len(tokenize(text)) == 1


@given(same_sign_durations())
def test_formatting_is_stable(duration: Duration) -> None:
    assert str(duration) == str(Duration(**vars_of(duration)))


@given(same_sign_durations())
def test_normalization_is_idempotent(duration: Duration) -> None:
    once = duration.normalized()
    assert once == once.normalized()
    assert str(once) == str(once.normalized())


def vars_of(duration: Duration) -> dict[str, int]:
    return {
        "months": duration.months,
        "days": duration.days,
        "bdays": duration.bdays,
        "millis": duration.millis,
    }


@given(st.integers(min_value=1, max_value=MAX_DAYS), st.integers(min_value=1, max_value=10**9))
def test_a_mixed_sign_duration_formats_stably(days: int, millis: int) -> None:
    duration = Duration(days=days, millis=-millis)
    assert str(duration) == str(duration)
    assert " " in str(duration)


# --------------------------------------------------------------------------
# arithmetic identities
# --------------------------------------------------------------------------


@given(exact_durations())
def test_adding_then_subtracting_an_exact_duration_returns_the_instant(
    duration: Duration,
) -> None:
    start = Instant.from_wall_clock(NY, TEST_NOW.replace(tzinfo=None))
    assert (start + duration - duration).moment == start.moment


@given(same_sign_durations())
def test_negating_twice_is_the_identity(duration: Duration) -> None:
    negated = -duration
    assert -negated == duration


@given(exact_durations(), st.integers(min_value=1, max_value=1000))
def test_scaling_up_then_down_returns_an_exact_duration(duration: Duration, factor: int) -> None:
    assert duration * float(factor) / float(factor) == duration


@given(exact_durations(), exact_durations())
def test_addition_of_durations_commutes(left: Duration, right: Duration) -> None:
    assert left + right == right + left


@given(same_sign_durations())
def test_a_duration_compares_equal_to_itself(duration: Duration) -> None:
    assert duration.compare(duration) == 0


# --------------------------------------------------------------------------
# colon literals
# --------------------------------------------------------------------------

hours = st.integers(min_value=0, max_value=99)
minutes = st.integers(min_value=0, max_value=59)
seconds = st.integers(min_value=0, max_value=59)


@given(hours, minutes, seconds)
def test_a_three_field_colon_literal_is_hours_minutes_seconds(
    hour: int, minute: int, second: int
) -> None:
    assume((hour, minute, second) != (0, 0, 0))
    text = f"{hour}:{minute:02d}:{second:02d}h"
    assert evaluate(text) == D(h=hour, m=minute, s=second)


@given(hours, minutes)
def test_a_bare_two_field_colon_literal_is_hours_and_minutes_as_a_duration(
    hour: int, minute: int
) -> None:
    assume((hour, minute) != (0, 0))
    assert evaluate(f"{hour}:{minute:02d}h") == D(h=hour, m=minute)


@given(minutes, seconds)
def test_the_m_suffix_shifts_the_units_down(minute: int, second: int) -> None:
    assume((minute, second) != (0, 0))
    assert evaluate(f"{minute}:{second:02d}m") == D(m=minute, s=second)


@given(minutes, seconds)
def test_a_leading_colon_shifts_the_units_down_the_same_way(minute: int, second: int) -> None:
    """The two explicit forms are two spellings of one meaning."""
    assume((minute, second) != (0, 0))
    text = f"{minute}:{second:02d}"
    assert evaluate(f":{text}") == evaluate(f"{text}m")


@given(seconds)
def test_two_leading_colons_leave_only_seconds(second: int) -> None:
    assume(second != 0)
    assert evaluate(f"::{second:02d}") == D(s=second)


@given(st.integers(min_value=0, max_value=23), minutes, seconds)
def test_a_valid_clock_reading_lands_on_the_right_wall_clock(
    hour: int, minute: int, second: int
) -> None:
    value = evaluate(f"{hour:02d}:{minute:02d}:{second:02d} in America/New_York")
    assert isinstance(value, Instant)
    assert value.wall_clock().time().isoformat() == f"{hour:02d}:{minute:02d}:{second:02d}"


@given(hours, minutes)
def test_a_colon_duration_subtracted_from_an_instant_moves_it_back(hour: int, minute: int) -> None:
    assume((hour, minute) != (0, 0))
    env = fresh_env()
    before = evaluate_line("now", env)
    after = evaluate_line(f"now - {hour}:{minute:02d}h", env)
    assert isinstance(before, Instant)
    assert isinstance(after, Instant)
    assert before.elapsed_since(after) == D(h=hour, m=minute)
