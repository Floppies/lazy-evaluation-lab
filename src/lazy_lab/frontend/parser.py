from __future__ import annotations

from ..ast.nodes import Expr, IntLiteral, BoolLiteral, Var
from .tokens import Token, TokenKind
from .lexer import tokenize
from .errors import ParserError


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

    def _parse_expression(self) -> Expr:
        return self._parse_atom()

    def parse_expression(self) -> Expr:
        expression = self._parse_expression()
        self._expect(TokenKind.EOF)
        return expression


def parse_expression(source: str) -> Expr:
    """Tokenize source and parse one complete expression."""
    tokens = tokenize(source)
    parser = _Parser(tokens)
    return parser.parse_expression()
