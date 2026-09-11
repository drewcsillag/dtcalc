"""The single error type used everywhere in dtcalc.

Every layer — lexer, parser, resolver, evaluator, builtins — raises
:class:`DtcalcError`.  Keeping one type means the REPL has exactly one place
that knows how to turn a failure into something a person can read, and the
caret rendering is written and tested once.
"""

from __future__ import annotations

__all__ = ["DtcalcError"]

# Tabs are expanded to a single space so that a character offset into the
# source line is also a column in the rendered output.  Anything wider would
# require mapping offsets through the expansion.
_TAB_REPLACEMENT = " "

_INDENT = "  "


class DtcalcError(Exception):
    """An error with an optional span into the source line that caused it.

    ``start`` and ``end`` are character offsets into the input line, with
    ``end`` exclusive.  They are supplied together or not at all: an error
    without a span renders as a bare message.
    """

    def __init__(self, message: str, start: int | None = None, end: int | None = None) -> None:
        super().__init__(message)
        if (start is None) != (end is None):
            raise ValueError("a span needs both start and end, or neither")
        self.message = message
        self.start = start
        self.end = end

    @property
    def has_span(self) -> bool:
        return self.start is not None

    def render(self, line: str) -> str:
        """Format the error, underlining the offending span of ``line``."""
        header = f"error: {self.message}"
        if self.start is None or self.end is None:
            return header

        display = line.replace("\t", _TAB_REPLACEMENT)

        # A parser reporting "unexpected end of input" points one past the last
        # character, so the caret is allowed to sit just beyond the line.
        start = max(0, min(self.start, len(display)))
        end = max(start, min(self.end, len(display)))
        width = max(1, end - start)

        underline = " " * start + "^" * width
        return f"{header}\n{_INDENT}{display}\n{_INDENT}{underline}"
