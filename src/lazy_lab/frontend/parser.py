from __future__ import annotations

from .tokens import Token, TokenKind
from .lexer import tokenize
from .errors import ParserError
from ..source import SourceSpan
from ..ast.nodes import (
    Expr,
    IntLiteral,
    BoolLiteral,
    Var,
    UnaryOp,
    BinaryOp,
    Application,
)

_COMPARISON_KINDS = (
    TokenKind.EQEQ,
    TokenKind.NEQ,
    TokenKind.LT,
    TokenKind.LTE,
    TokenKind.GT,
    TokenKind.GTE,
)

_ATOM_STARTS = {
    TokenKind.INT,
    TokenKind.TRUE,
    TokenKind.FALSE,
    TokenKind.IDENT,
    TokenKind.LPAREN,
}

class _Parser:
    def __init__(self, tokens: tuple[Token, ...]):
        self.tokens = tokens
        self.index = 0

    def _peek(self) -> Token:
        return self.tokens[self.index]

    def _advance(self) -> Token:
        token = self._peek()

        if token.kind != TokenKind.EOF:
            self.index += 1

        return token

    def _match(self, *kinds: TokenKind) -> Token | None:
        token = self._peek()

        if token.kind in kinds:
            return self._advance()

        return None

    def _expect(self, kind: TokenKind) -> Token:
        token = self._peek()

        if token.kind != kind:
            raise ParserError(
                f"Expected {kind.name}, found {token.kind.name}",
                token,
            )

        return self._advance()

    def _span_from(self, start: Token) -> SourceSpan:
        end = self.tokens[self.index - 1]

        return SourceSpan(
            start_line=start.span.start_line,
            start_column=start.span.start_column,
            end_line=end.span.end_line,
            end_column=end.span.end_column,
        )

    def _parse_atom(self) -> Expr:
        token = self._peek()

        if token.kind == TokenKind.INT:
            self._advance()

            return IntLiteral(
                value=int(token.lexeme),
                span=token.span,
            )

        if token.kind == TokenKind.TRUE:
            self._advance()

            return BoolLiteral(
                value=True,
                span=token.span,
            )

        if token.kind == TokenKind.FALSE:
            self._advance()

            return BoolLiteral(
                value=False,
                span=token.span,
            )

        if token.kind == TokenKind.IDENT:
            self._advance()

            return Var(
                name=token.lexeme,
                span=token.span,
            )

        if self._match(TokenKind.LPAREN):
            expression = self._parse_expression()
            self._expect(TokenKind.RPAREN)
            return expression

        raise ParserError(
            f"Expected an expression, found {token.kind.name}",
            token,
        )

    def _parse_application(self) -> Expr:
        start = self._peek()
        expression = self._parse_atom()

        while self._peek().kind in _ATOM_STARTS:
            argument = self._parse_atom()

            expression = Application(
                function=expression,
                argument=argument,
                span=self._span_from(start),
            )

        return expression

    def _parse_unary(self) -> Expr:
        operator = self._match(TokenKind.MINUS)

        if operator is not None:
            operand = self._parse_unary()

            return UnaryOp(
                operator="-",
                operand=operand,
                span=self._span_from(operator),
            )

        return self._parse_application()

    def _parse_multiplicative(self) -> Expr:
        start = self._peek()
        left = self._parse_unary()

        while operator := self._match(TokenKind.STAR):
            right = self._parse_unary()

            left = BinaryOp(
                operator=operator.lexeme,
                left=left,
                right=right,
                span=self._span_from(start),
            )

        return left

    def _parse_additive(self) -> Expr:
        start = self._peek()
        left = self._parse_multiplicative()

        while operator := self._match(
            TokenKind.PLUS,
            TokenKind.MINUS,
        ):
            right = self._parse_multiplicative()

            left = BinaryOp(
                operator=operator.lexeme,
                left=left,
                right=right,
                span=self._span_from(start),
            )

        return left

    def _parse_cons(self) -> Expr:
        start = self._peek()
        left = self._parse_additive()

        if self._match(TokenKind.COLON):
            right = self._parse_cons()

            return BinaryOp(
                operator=":",
                left=left,
                right=right,
                span=self._span_from(start),
            )

        return left

    def _parse_expression(self) -> Expr:
        return self._parse_comparison()

    def parse_expression(self) -> Expr:
        expression = self._parse_expression()
        self._expect(TokenKind.EOF)
        return expression

    def _parse_comparison(self) -> Expr:
        start = self._peek()
        left = self._parse_cons()

        operator = self._match(*_COMPARISON_KINDS)

        if operator is None:
            return left

        right = self._parse_cons()

        if self._peek().kind in _COMPARISON_KINDS:
            raise ParserError(
                "Chained comparisons are not supported",
                self._peek(),
            )

        return BinaryOp(
            operator=operator.lexeme,
            left=left,
            right=right,
            span=self._span_from(start),
        )

def parse_expression(source: str) -> Expr:
    """Tokenize source and parse one complete expression."""
    tokens = tokenize(source)
    parser = _Parser(tokens)
    return parser.parse_expression()
