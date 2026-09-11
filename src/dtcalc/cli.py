"""Command-line entry point.

Three modes:

``dtcalc 'now + 7h'``
    Evaluate one expression and exit.

``dtcalc`` with piped input
    Evaluate each line.  An error on one line does not stop the rest, but the
    process still exits non-zero — which is what makes the mode usable in a
    script without silently swallowing mistakes.

``dtcalc`` on a terminal
    The interactive REPL.

``--transcript`` echoes each input line with a prompt and routes errors to
stdout instead of stderr, so a whole session can be captured as one stream.
That is how the golden tests pin the user-visible output.

``DTCALC_TZ`` and ``DTCALC_NOW`` override the display zone and freeze the
clock.  They exist so that output can be made reproducible — the golden
transcripts could not otherwise mention ``now``.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from dtcalc import __version__
from dtcalc.ast import sexpr
from dtcalc.clock import Clock, FixedClock, SystemClock
from dtcalc.env import Env
from dtcalc.errors import DtcalcError
from dtcalc.format import Style, choose_style
from dtcalc.lexer import tokenize
from dtcalc.parser import parse
from dtcalc.resolve import resolve
from dtcalc.session import Outcome, execute_line
from dtcalc.zones import local_zone, resolve_zone

__all__ = ["build_env", "main"]

PROMPT = "dtcalc> "

_NOW_ENV = "DTCALC_NOW"
_TZ_ENV = "DTCALC_TZ"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dtcalc",
        description="Interactive calculator for dates, times, durations and timezones.",
    )
    parser.add_argument(
        "expression",
        nargs="?",
        help="evaluate this expression and exit; omit it to read stdin or start the REPL",
    )
    parser.add_argument("--version", action="version", version=f"dtcalc {__version__}")
    parser.add_argument(
        "--transcript",
        action="store_true",
        help="echo each input line with a prompt and send errors to stdout",
    )
    parser.add_argument("--no-color", action="store_true", help="never colourise output")
    parser.add_argument(
        "--dump-tokens",
        metavar="EXPR",
        help="print the token stream for EXPR and exit (a debugging aid)",
    )
    parser.add_argument(
        "--dump-ast",
        metavar="EXPR",
        help="print EXPR's syntax tree before and after resolution, then exit",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.dump_tokens is not None:
        return _dump_tokens(args.dump_tokens)

    if args.dump_ast is not None:
        return _dump_ast(args.dump_ast)

    try:
        env = build_env()
    except DtcalcError as error:
        print(error.render(""), file=sys.stderr)
        return 1

    style = choose_style(no_color=args.no_color)

    if args.expression is not None:
        return _run_one(args.expression, env, style, to_stdout=False)

    if not sys.stdin.isatty():
        return _run_pipe(env, style, transcript=args.transcript)

    from dtcalc.repl import run_repl

    return run_repl(env, style)


# --------------------------------------------------------------------------
# environment
# --------------------------------------------------------------------------


def build_env() -> Env:
    """Assemble the starting environment, honouring the test overrides.

    ``DTCALC_TZ`` is read first, because a bare ``DTCALC_NOW`` with no offset
    is a wall-clock reading and needs a zone to be read in.
    """
    zone = _display_zone()
    return Env(clock=_clock(zone), zone=zone)


def _display_zone() -> ZoneInfo:
    override = os.environ.get(_TZ_ENV)
    if override:
        try:
            return resolve_zone(override)
        except DtcalcError as exc:
            raise DtcalcError(f"{_TZ_ENV} is set to {override!r}: {exc.message}") from exc
    return local_zone()


def _clock(zone: ZoneInfo) -> Clock:
    override = os.environ.get(_NOW_ENV)
    if not override:
        return SystemClock()
    try:
        parsed = datetime.fromisoformat(override)
    except ValueError as exc:
        raise DtcalcError(
            f"{_NOW_ENV} is set to {override!r}, which is not an ISO date and time"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    return FixedClock(parsed)


# --------------------------------------------------------------------------
# evaluation modes
# --------------------------------------------------------------------------


def _run_one(source: str, env: Env, style: Style, *, to_stdout: bool) -> int:
    result = execute_line(source, env, style)
    stream = sys.stdout if (to_stdout or not result.failed) else sys.stderr
    for line in result.lines:
        print(line, file=stream)
    return 1 if result.failed else 0


def _run_pipe(env: Env, style: Style, *, transcript: bool) -> int:
    """Evaluate every line of stdin, reporting failure without stopping.

    Continuing past an error is what makes the mode useful for a batch of
    expressions; the non-zero exit is what stops that being silent.
    """
    status = 0
    for raw in sys.stdin:
        line = raw.rstrip("\n")
        if transcript:
            print(f"{style.prompt(PROMPT)}{line}")
        result = execute_line(line, env, style)
        if result.outcome is Outcome.QUIT:
            break
        stream = sys.stdout if (transcript or not result.failed) else sys.stderr
        for text in result.lines:
            print(text, file=stream)
        if result.failed:
            status = 1
    return status


# --------------------------------------------------------------------------
# debugging aids
# --------------------------------------------------------------------------


def _dump_tokens(source: str) -> int:
    try:
        tokens = tokenize(source)
    except DtcalcError as error:
        print(error.render(source), file=sys.stderr)
        return 1
    for token in tokens:
        span = f"{token.start}-{token.end}"
        value = "" if token.value is None else f"  = {token.value!r}"
        print(f"{span:>8}  {token.kind.name:<14} {token.text!r}{value}")
    return 0


def _dump_ast(source: str) -> int:
    """Show the tree twice, so the resolution pass is visible in isolation.

    The parser leaves colon literals undecided; printing before and after is
    the quickest way to see which reading a given context produced.
    """
    try:
        parsed = parse(source)
        print(f"parsed:   {sexpr(parsed)}")
        print(f"resolved: {sexpr(resolve(parsed, {}))}")
    except DtcalcError as error:
        print(error.render(source), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via __main__.py
    raise SystemExit(main())
