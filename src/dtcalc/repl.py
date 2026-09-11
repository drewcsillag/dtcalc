"""The interactive REPL.

Everything except the readline wiring lives elsewhere — line execution and
meta-commands are in :mod:`dtcalc.session`, and the completer below is a pure
function of ``(line, cursor, env)``.  What is left here is the loop, the
history file, and the terminal's two interrupts.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path
from typing import Final

from dtcalc.builtins import SIGNATURES
from dtcalc.env import Env
from dtcalc.format import FORMATS, PLAIN, Style
from dtcalc.session import Outcome, execute_line
from dtcalc.zones import CURATED_ALIASES, all_zone_names

__all__ = ["completions", "readline_prompt", "run_repl"]

PROMPT: Final = "dtcalc> "

HISTORY_FILE: Final = Path.home() / ".dtcalc_history"
_HISTORY_LENGTH: Final = 2000

_KEYWORDS: Final = (
    "now",
    "today",
    "tomorrow",
    "yesterday",
    "upcoming",
    "previous",
    "in",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

_META_COMMANDS: Final = (":help", ":vars", ":zones", ":tz", ":fmt", ":q")

# A word under the cursor: identifier characters plus the slash and colon that
# zone names and commands use.
_WORD = re.compile(r"[A-Za-z0-9_/:]+$")

# The operators after which a zone name is expected rather than a value.
_ZONE_CONTEXT = re.compile(r"(?:\bin\b|@|:tz)\s+[A-Za-z0-9_/]*$")
_FORMAT_CONTEXT = re.compile(r":fmt\s+[a-z]*$")


def readline_prompt(text: str, style: Style, *, supports_marks: bool = True) -> str:
    """Colour the prompt only where the local readline can cope with it.

    GNU readline works out the cursor column by counting the prompt's
    characters, so escape sequences must be bracketed in \001 and \002 to be
    skipped.  There, colour is free.

    libedit — what macOS ships — has no working equivalent, and measuring both
    forms on a pty shows there is no way to have both:

    * raw escape codes colour correctly but are *counted*, so on a wrapped
      line Ctrl-A emits ``\x1b[18G`` instead of ``\x1b[9G`` and the cursor
      ends up nine columns adrift of where libedit thinks it is;
    * the \001/\002 form counts correctly but libedit prints the markers,
      putting the colour before the prompt text and re-emitting escapes on
      every backspace.

    So under libedit the prompt is left plain.  A cursor that lands where you
    press Ctrl-A matters more than a cyan prompt; results and errors are still
    coloured.
    """
    if not supports_marks:
        return text
    coloured = style.prompt(text)
    if coloured == text:
        return text
    prefix, _, rest = coloured.partition(text)
    return f"\001{prefix}\002{text}\001{rest}\002"


# --------------------------------------------------------------------------
# completion
# --------------------------------------------------------------------------


def completions(line: str, cursor: int, env: Env) -> list[str]:
    """Candidates for the word ending at ``cursor``.

    Context-sensitive in three ways: after ``in``, ``@`` or ``:tz`` the
    candidates are zone names, after ``:fmt`` they are format names, and
    otherwise they are the names in scope.  An empty prefix offers nothing,
    since listing every name is noise rather than help.
    """
    head = line[:cursor]
    match = _WORD.search(head)
    prefix = match.group() if match else ""
    if not prefix:
        return []

    if prefix.startswith(":"):
        return _matching(prefix, _META_COMMANDS)

    before = head[: match.start()] if match else head
    if _FORMAT_CONTEXT.search(head):
        return _matching(prefix, FORMATS)
    if _ZONE_CONTEXT.search(f"{before}{prefix}"):
        return _zone_candidates(prefix)

    names = (*env.variables, *SIGNATURES, *_KEYWORDS)
    return _matching(prefix, names)


def _matching(prefix: str, candidates: Iterable[str]) -> list[str]:
    lowered = prefix.lower()
    return sorted({name for name in candidates if name.lower().startswith(lowered)})


def _zone_candidates(prefix: str) -> list[str]:
    """Zone names for a prefix: curated aliases first, IANA names otherwise.

    Offering both spellings at once is worse than useless — ``Toky`` matches
    ``Tokyo`` and ``Asia/Tokyo``, which share no common prefix, so readline
    completes nothing and rings the bell.  The aliases exist precisely to be
    the short memorable spellings, so they win outright when one matches, and
    the full IANA list is there for everything else.

    IANA names also match on their last segment, which is what makes
    ``New_Yo`` find ``America/New_York`` without remembering the region.
    """
    lowered = prefix.lower()
    aliases = sorted(alias for alias in CURATED_ALIASES if alias.lower().startswith(lowered))
    if aliases:
        return aliases

    return sorted(
        zone
        for zone in all_zone_names()
        if zone.lower().startswith(lowered) or zone.rpartition("/")[2].lower().startswith(lowered)
    )


# --------------------------------------------------------------------------
# the loop
# --------------------------------------------------------------------------


def run_repl(env: Env, style: Style = PLAIN) -> int:
    """Read, evaluate and print until end of input or ``:q``."""
    readline = _setup_readline(env)
    prompt = readline_prompt(PROMPT, style, supports_marks=not _is_libedit(readline))

    print("dtcalc — :help for the language, :q to quit")
    try:
        while True:
            try:
                line = input(prompt)
            except EOFError:
                print()
                return 0
            except KeyboardInterrupt:
                # Abandon the current line without leaving the REPL, which is
                # what Ctrl-C means in every other shell.
                print("^C")
                continue

            result = execute_line(line, env, style)
            if result.outcome is Outcome.QUIT:
                return 0
            for text in result.lines:
                print(text)
    finally:
        _save_history(readline)


def _setup_readline(env: Env) -> object:
    """Wire up history and completion, tolerating a missing readline."""
    try:
        import readline
    except ImportError:  # pragma: no cover - readline is present on macOS and Linux
        return None

    # A missing or corrupt history file is not worth mentioning, let alone
    # failing over.
    with suppress(OSError, ValueError):
        readline.read_history_file(HISTORY_FILE)
    readline.set_history_length(_HISTORY_LENGTH)

    def complete(text: str, state: int) -> str | None:
        line = readline.get_line_buffer()
        cursor = readline.get_endidx()
        candidates = completions(line, cursor, env)
        # Readline replaces only `text`, so trim the part already typed when
        # the candidate is a longer word such as a slash-separated zone.
        prefix_length = len(_prefix_of(line, cursor)) - len(text)
        trimmed = [candidate[prefix_length:] for candidate in candidates]
        return trimmed[state] if state < len(trimmed) else None

    readline.set_completer(complete)
    readline.set_completer_delims(" \t\n+-*/%(),=<>!")
    # libedit (what macOS ships) and GNU readline spell this differently, and
    # binding the wrong one silently does nothing.
    binding = "bind ^I rl_complete" if _is_libedit(readline) else "tab: complete"
    readline.parse_and_bind(binding)
    return readline


def _prefix_of(line: str, cursor: int) -> str:
    match = _WORD.search(line[:cursor])
    return match.group() if match else ""


def _is_libedit(readline: object) -> bool:
    return "libedit" in (getattr(readline, "__doc__", "") or "")


def _save_history(readline: object) -> None:
    if readline is None:
        return
    write = getattr(readline, "write_history_file", None)
    if write is None:  # pragma: no cover - always present when readline is
        return
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        write(os.fspath(HISTORY_FILE))
    except OSError:  # pragma: no cover - an unwritable home is not fatal
        pass
