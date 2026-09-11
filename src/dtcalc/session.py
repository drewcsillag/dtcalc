"""One line in, one block of output out.

Shared by the piped and interactive front ends, so that a transcript
captured through a pipe behaves exactly like a session typed at a terminal.
The REPL adds only readline: history, editing and completion.

Meta-command dispatch is a pure function of ``(line, env)`` returning the
lines to print, which is what makes it testable without a terminal.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Final

from dtcalc.builtins import SIGNATURES
from dtcalc.env import Env
from dtcalc.errors import DtcalcError
from dtcalc.evaluator import evaluate_line
from dtcalc.format import CLOCKS, FORMATS, Style, format_value, render
from dtcalc.lexer import is_meta_command, tokenize
from dtcalc.zones import resolve_zone, search_zones

__all__ = ["Outcome", "Result", "execute_line", "help_text"]

_MAX_LISTED_ZONES: Final = 30


class Outcome(Enum):
    """What the front end should do next."""

    OK = auto()
    ERROR = auto()
    QUIT = auto()
    NOTHING = auto()


@dataclass(frozen=True, slots=True)
class Result:
    outcome: Outcome
    lines: tuple[str, ...] = ()

    @property
    def failed(self) -> bool:
        return self.outcome is Outcome.ERROR


def execute_line(line: str, env: Env, style: Style) -> Result:
    """Run one input line against ``env``, which it may mutate."""
    if is_meta_command(line):
        return _meta(line.strip(), env, style)

    try:
        if not tokenize(line):
            return Result(Outcome.NOTHING)
    except DtcalcError as error:
        return Result(Outcome.ERROR, (style.error(error.render(line)),))

    try:
        value = evaluate_line(line, env)
    except DtcalcError as error:
        return Result(Outcome.ERROR, (style.error(error.render(line)),))

    rendered = render(value, env.display())
    # The value is coloured; an advisory note is left plain, since it is
    # commentary rather than the answer.
    return Result(Outcome.OK, (style.result(rendered[0]), *rendered[1:]))


# --------------------------------------------------------------------------
# meta-commands
# --------------------------------------------------------------------------


def _meta(line: str, env: Env, style: Style) -> Result:
    command, _, argument = line[1:].partition(" ")
    argument = argument.strip()

    match command:
        case "q" | "quit" | "exit":
            return Result(Outcome.QUIT)
        case "help" | "h":
            return Result(Outcome.OK, tuple(help_text()))
        case "vars":
            return Result(Outcome.OK, tuple(_list_variables(env)))
        case "zones":
            return _zones(argument, style)
        case "tz":
            return _set_zone(argument, env, style)
        case "fmt":
            return _set_format(argument, env, style)
        case _:
            return Result(
                Outcome.ERROR,
                (style.error(f"error: unknown command ':{command}'; try :help"),),
            )


def _list_variables(env: Env) -> list[str]:
    if not env.variables:
        return ["(no variables set)"]
    width = max(len(name) for name in env.variables)
    return [
        f"{name:<{width}}  {format_value(value, env.display())}"
        for name, value in sorted(env.variables.items())
    ]


def _zones(substring: str, style: Style) -> Result:
    if not substring:
        return Result(
            Outcome.ERROR,
            (style.error("error: :zones needs something to search for, e.g. :zones tokyo"),),
        )
    matches = search_zones(substring)
    if not matches:
        return Result(Outcome.OK, (f"no timezone matches {substring!r}",))
    shown = matches[:_MAX_LISTED_ZONES]
    lines = list(shown)
    if len(matches) > len(shown):
        lines.append(f"... and {len(matches) - len(shown)} more")
    return Result(Outcome.OK, tuple(lines))


def _set_zone(name: str, env: Env, style: Style) -> Result:
    if not name:
        return Result(Outcome.OK, (f"display zone is {env.zone}",))
    try:
        env.zone = resolve_zone(name)
    except DtcalcError as error:
        return Result(Outcome.ERROR, (style.error(f"error: {error.message}"),))
    return Result(Outcome.OK, (f"display zone is now {env.zone}",))


def _set_format(argument: str, env: Env, style: Style) -> Result:
    """``:fmt`` sets the instant format, the clock convention, or both.

    Both settings live on one command because they answer the same question —
    how should a time be written — and keeping them together means ``:fmt``
    alone reports the whole answer.
    """
    if not argument:
        return Result(Outcome.OK, (_describe_format(env),))

    words = argument.split()
    fmt: str | None = None
    clock: str | None = None
    for word in words:
        if word in CLOCKS:
            clock = word
        elif word in FORMATS:
            fmt = word
        else:
            return Result(
                Outcome.ERROR,
                (
                    style.error(
                        f"error: unknown setting {word!r}; formats are "
                        f"{', '.join(FORMATS)}; clocks are {', '.join(CLOCKS)}"
                    ),
                ),
            )

    if fmt is not None:
        env.fmt = fmt
    if clock is not None:
        env.clock_style = clock
    return Result(Outcome.OK, (f"format is now {env.fmt}, {env.clock_style} clock",))


def _describe_format(env: Env) -> str:
    return f"format is {env.fmt}, {env.clock_style} clock"


def help_text() -> list[str]:
    """The ``:help`` output, which doubles as the language's cheat sheet."""
    return [
        "values      instants, durations, numbers, booleans",
        "instants    now, today, tomorrow, yesterday, 2026-05-23T12:15:13,",
        "            2026-05-23, today 09:00, upcoming friday, previous 15th,",
        "            epoch(1789073107), epochms(...)",
        "clock times 12:15 or 16:00, and 4p 4a 4pm 4:30pm (12a is midnight,",
        "            12p is noon)",
        "durations   3w2h5m, 250ms, 1.5s, 3bd  (ms s m h | d w | mo y | bd)",
        "colon forms 12:15 is 12h15m or 12:15:00 depending on context;",
        "            12:15m is 12m15s, :12:15 is 12m15s, ::15 is 15s",
        "operators   + - * / %, comparisons, in (show in a zone)",
        "            @ attaches a zone (12:13 @ sf) or a time (foo @ 4p, which",
        "            keeps foo's date and changes the time)",
        "            tightest first: @  then * / %  then + -  then compare  then in",
        "functions   " + ", ".join(sorted(SIGNATURES)),
        "ladders     ms/s/m/h are exact; d/w and mo/y are calendar; bd is business",
        "            days.  They never convert, so 8h * 3 is 24h and never 1d.",
        "commands    :help  :vars  :zones <text>  :tz <zone>  :q",
        "            :fmt iso|human|unix|timeonly and/or 24h|12h",
        "            (the clock applies to human and timeonly, not to iso)",
    ]
