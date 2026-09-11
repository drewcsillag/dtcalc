"""Recursive-descent parser.

Precedence, tightest first::

    @                       attach a zone, or a time of day
    * / %
    + -
    < <= > >= == !=         non-associative, so a < b < c is refused
    in                      convert for display
    =                       assignment

``@`` attaches either a zone (``12:13 @ sf`` — read this clock reading as San
Francisco's) or a time of day (``foo @ 4p`` — keep foo's date, use this time).
The two never collide, because a zone name cannot begin with a digit.

``in`` deliberately sits loosest and takes a bare zone *name* on the right
rather than an expression, because zones are not values in this language.
That is why ``now + 1d in Tokyo`` groups the way it reads, and why
``now in Tokyo + 2h`` is a parse error rather than a surprise.
"""

from __future__ import annotations

from typing import Final

from dtcalc.ast import (
    Assign,
    Attach,
    Binary,
    Call,
    ColonLit,
    Convert,
    DateAtTime,
    DateTimeLit,
    DayKeyword,
    DurationLit,
    Negate,
    Node,
    NowLit,
    NumberLit,
    OrdinalRef,
    TimeOfDay,
    VarRef,
    WeekdayRef,
)
from dtcalc.duration import Duration
from dtcalc.errors import DtcalcError
from dtcalc.lexer import (
    ClockLiteral,
    ColonLiteral,
    DateTimeLiteral,
    Token,
    TokenKind,
    tokenize,
)

__all__ = ["parse"]

K = TokenKind

_COMPARISONS: Final[dict[TokenKind, str]] = {
    K.LT: "<",
    K.LE: "<=",
    K.GT: ">",
    K.GE: ">=",
    K.EQ: "==",
    K.NE: "!=",
}

_ADDITIVE: Final[dict[TokenKind, str]] = {K.PLUS: "+", K.MINUS: "-"}

_MULTIPLICATIVE: Final[dict[TokenKind, str]] = {K.STAR: "*", K.SLASH: "/", K.PERCENT: "%"}

_DAY_KEYWORDS: Final[dict[TokenKind, tuple[str, int]]] = {
    K.TODAY: ("today", 0),
    K.TOMORROW: ("tomorrow", 1),
    K.YESTERDAY: ("yesterday", -1),
}

# Nodes that name a day and so may be narrowed by a following time of day.
_TAKES_A_TIME: Final = (DayKeyword, WeekdayRef, OrdinalRef)


def parse(source: str) -> Node:
    """Parse one line into an unresolved AST."""
    return _Parser(source, tokenize(source)).parse()


class _Parser:
    def __init__(self, source: str, tokens: list[Token]) -> None:
        self._source = source
        self._tokens = tokens
        self._index = 0

    # ------------------------------------------------------------------
    # token plumbing
    # ------------------------------------------------------------------

    @property
    def _current(self) -> Token | None:
        return self._tokens[self._index] if self._index < len(self._tokens) else None

    def _at(self, *kinds: TokenKind) -> bool:
        token = self._current
        return token is not None and token.kind in kinds

    def _take(self) -> Token:
        token = self._current
        assert token is not None  # callers check before taking
        self._index += 1
        return token

    def _eof_span(self) -> tuple[int, int]:
        return len(self._source), len(self._source) + 1

    def _expect(self, kind: TokenKind, what: str) -> Token:
        token = self._current
        if token is None:
            start, end = self._eof_span()
            raise DtcalcError(f"expected {what} but the line ended", start, end)
        if token.kind is not kind:
            raise DtcalcError(f"expected {what} but found {token.text!r}", token.start, token.end)
        return self._take()

    # ------------------------------------------------------------------
    # grammar
    # ------------------------------------------------------------------

    def parse(self) -> Node:
        if not self._tokens:
            raise DtcalcError("nothing to evaluate")
        self._reject_keyword_assignment()
        node = self._assignment()
        leftover = self._current
        if leftover is not None:
            raise DtcalcError(
                f"unexpected {leftover.text!r} after a complete expression",
                leftover.start,
                leftover.end,
            )
        return node

    def _assignment(self) -> Node:
        if self._at(K.IDENT) and self._peek_is(1, K.ASSIGN):
            name = self._take()
            self._take()  # '='
            value = self._convert()
            return Assign(name.start, value.end, name.text, value)
        return self._convert()

    def _reject_keyword_assignment(self) -> None:
        """Explain ``now = 3h`` rather than complaining about the ``=``.

        Without this the parser reports an unexpected ``=``, which describes
        the symptom and not the cause.
        """
        if len(self._tokens) < 2 or self._tokens[1].kind is not K.ASSIGN:
            return
        target = self._tokens[0]
        if target.kind is not K.IDENT:
            raise DtcalcError(
                f"{target.text!r} is a keyword, so it cannot be a variable name",
                target.start,
                target.end,
            )

    def _peek_is(self, offset: int, kind: TokenKind) -> bool:
        position = self._index + offset
        return position < len(self._tokens) and self._tokens[position].kind is kind

    def _convert(self) -> Node:
        node = self._comparison()
        if self._at(K.IN):
            self._take()
            zone, end = self._zone_name()
            return Convert(node.start, end, node, zone)
        return node

    def _comparison(self) -> Node:
        node = self._additive()
        token = self._current
        if token is not None and token.kind in _COMPARISONS:
            self._take()
            right = self._additive()
            node = Binary(node.start, right.end, _COMPARISONS[token.kind], node, right)
            follow = self._current
            if follow is not None and follow.kind in _COMPARISONS:
                raise DtcalcError(
                    "comparisons do not chain; compare two things at a time",
                    follow.start,
                    follow.end,
                )
        return node

    def _additive(self) -> Node:
        node = self._multiplicative()
        while (token := self._current) is not None and token.kind in _ADDITIVE:
            self._take()
            right = self._multiplicative()
            node = Binary(node.start, right.end, _ADDITIVE[token.kind], node, right)
        return node

    def _multiplicative(self) -> Node:
        node = self._unary()
        while (token := self._current) is not None and token.kind in _MULTIPLICATIVE:
            self._take()
            right = self._unary()
            node = Binary(node.start, right.end, _MULTIPLICATIVE[token.kind], node, right)
        return node

    def _unary(self) -> Node:
        if self._at(K.MINUS):
            token = self._take()
            operand = self._unary()
            return Negate(token.start, operand.end, operand)
        if self._at(K.PLUS):
            # A leading plus is noise; drop it rather than build a node.
            self._take()
            return self._unary()
        return self._attach()

    def _attach(self) -> Node:
        node = self._primary()
        if not self._at(K.AT):
            return node

        self._take()  # '@'
        # A clock reading after `@` means "keep the date, use this time"; an
        # identifier means "read this wall clock as being in that zone".
        if self._at(K.COLON_LITERAL, K.CLOCK):
            time = self._clock_reading()
            return DateAtTime(node.start, time.end, node, time)
        if self._at(K.IDENT):
            zone, end = self._zone_name()
            return Attach(node.start, end, node, zone)

        found = self._current
        where = f"but found {found.text!r}" if found is not None else "but the line ended"
        start, end = (found.start, found.end) if found is not None else self._eof_span()
        raise DtcalcError(
            f"expected a timezone name or a time of day after '@' {where}", start, end
        )

    def _clock_reading(self) -> Node:
        """A colon literal or a meridiem literal, as a time of day."""
        token = self._take()
        if token.kind is K.CLOCK:
            assert isinstance(token.value, ClockLiteral)
            return TimeOfDay(
                token.start,
                token.end,
                token.value.hour,
                token.value.minute,
                token.value.second,
                token.value.microsecond,
            )
        assert isinstance(token.value, ColonLiteral)
        return ColonLit(token.start, token.end, token.value, token.text)

    def _zone_name(self) -> tuple[str, int]:
        """A zone name: an identifier, possibly a slash-separated IANA path."""
        token = self._current
        if token is None:
            start, end = self._eof_span()
            raise DtcalcError("expected a timezone name but the line ended", start, end)
        if token.kind is not K.IDENT:
            raise DtcalcError(
                f"expected a timezone name but found {token.text!r}", token.start, token.end
            )
        self._take()
        parts = [token.text]
        end = token.end
        while self._at(K.SLASH):
            self._take()
            part = self._expect(K.IDENT, "the rest of the timezone name")
            parts.append(part.text)
            end = part.end
        return "/".join(parts), end

    def _primary(self) -> Node:
        token = self._current
        if token is None:
            start, end = self._eof_span()
            raise DtcalcError("expected an expression but the line ended", start, end)

        match token.kind:
            case K.NUMBER:
                self._take()
                assert isinstance(token.value, float)
                return NumberLit(token.start, token.end, token.value)

            case K.DURATION:
                self._take()
                assert isinstance(token.value, Duration)
                return DurationLit(token.start, token.end, token.value)

            case K.COLON_LITERAL:
                self._take()
                assert isinstance(token.value, ColonLiteral)
                return ColonLit(token.start, token.end, token.value, token.text)

            case K.CLOCK:
                return self._clock_reading()

            case K.DATETIME | K.DATE:
                self._take()
                assert isinstance(token.value, DateTimeLiteral)
                return DateTimeLit(token.start, token.end, token.value, token.text)

            case K.NOW:
                self._take()
                return NowLit(token.start, token.end)

            case K.TODAY | K.TOMORROW | K.YESTERDAY:
                self._take()
                name, offset = _DAY_KEYWORDS[token.kind]
                return self._maybe_time(DayKeyword(token.start, token.end, name, offset))

            case K.UPCOMING | K.PREVIOUS:
                return self._day_reference()

            case K.IDENT:
                self._take()
                if self._at(K.LPAREN):
                    return self._call(token)
                return VarRef(token.start, token.end, token.text)

            case K.LPAREN:
                self._take()
                inner = self._assignment()
                closing = self._closing_paren(token)
                return _respan(inner, token.start, closing.end)

            case _:
                raise DtcalcError(
                    f"unexpected {token.text!r} where an expression was expected",
                    token.start,
                    token.end,
                )

    def _closing_paren(self, opening: Token) -> Token:
        token = self._current
        if token is None:
            raise DtcalcError(
                "missing a closing parenthesis for this one", opening.start, opening.end
            )
        if token.kind is not K.RPAREN:
            raise DtcalcError(
                f"expected a closing parenthesis but found {token.text!r}",
                token.start,
                token.end,
            )
        return self._take()

    def _day_reference(self) -> Node:
        keyword = self._take()
        direction = "upcoming" if keyword.kind is K.UPCOMING else "previous"
        token = self._current
        if token is None:
            start, end = self._eof_span()
            raise DtcalcError(
                f"expected a weekday or a day of the month after {direction!r}", start, end
            )
        if token.kind is K.WEEKDAY:
            self._take()
            assert isinstance(token.value, int)
            node: Node = WeekdayRef(keyword.start, token.end, direction, token.value)
        elif token.kind is K.ORDINAL:
            self._take()
            assert isinstance(token.value, int)
            node = OrdinalRef(keyword.start, token.end, direction, token.value)
        else:
            raise DtcalcError(
                f"expected a weekday or a day of the month after {direction!r} "
                f"but found {token.text!r}",
                token.start,
                token.end,
            )
        return self._maybe_time(node)

    def _maybe_time(self, date: Node) -> Node:
        """Attach a following clock reading: ``upcoming friday 09:00``."""
        if not self._at(K.COLON_LITERAL, K.CLOCK):
            return date
        time = self._clock_reading()
        return DateAtTime(date.start, time.end, date, time)

    def _call(self, name: Token) -> Node:
        self._take()  # '('
        args: list[Node] = []
        if not self._at(K.RPAREN):
            args.append(self._convert())
            while self._at(K.COMMA):
                self._take()
                args.append(self._convert())
        closing = self._closing_paren(name)
        return Call(name.start, closing.end, name.text, tuple(args))


def _respan(node: Node, start: int, end: int) -> Node:
    """Widen a parenthesised node's span to include its brackets."""
    from dataclasses import replace

    return replace(node, start=start, end=end)
