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
    LambdaExpr,
    IfExpr,
    LocalBinding,
    LetExpr,
    ListLiteral,
    Program,
    Pattern,
    VarPattern,
    NilPattern,
    ConsPattern,
    ValueDefinition,
    FunctionEquation,
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
    TokenKind.LBRACKET,
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
                value=_decimal_to_int(token.lexeme),
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

        if token.kind == TokenKind.LBRACKET:
            return self._parse_list()

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

    def _parse_list(self) -> ListLiteral:
        start = self._expect(TokenKind.LBRACKET)
        elements: list[Expr] = []

        if self._peek().kind != TokenKind.RBRACKET:
            elements.append(self._parse_expression())

            while self._match(TokenKind.COMMA):
                elements.append(self._parse_expression())

        self._expect(TokenKind.RBRACKET)

        return ListLiteral(
            elements=tuple(elements),
            span=self._span_from(start),
        )

    def _parse_lambda(self) -> LambdaExpr:
        start = self._expect(TokenKind.BACKSLASH)

        parameters = []

        first = self._expect(TokenKind.IDENT)
        parameters.append(first.lexeme)

        while self._peek().kind == TokenKind.IDENT:
            parameters.append(self._advance().lexeme)

        self._expect(TokenKind.ARROW)

        body = self._parse_expression()

        return LambdaExpr(
            parameters=tuple(parameters),
            body=body,
            span=self._span_from(start),
        )

    def _parse_if(self) -> IfExpr:
        start = self._expect(TokenKind.IF)

        condition = self._parse_expression()

        self._expect(TokenKind.THEN)
        then_branch = self._parse_expression()

        self._expect(TokenKind.ELSE)
        else_branch = self._parse_expression()

        return IfExpr(
            condition=condition,
            then_branch=then_branch,
            else_branch=else_branch,
            span=self._span_from(start),
        )

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

    def _parse_local_binding(self) -> LocalBinding:
        start = self._expect(TokenKind.IDENT)
        name = start.lexeme

        parameters = []

        while self._peek().kind == TokenKind.IDENT:
            parameters.append(self._advance().lexeme)

        self._expect(TokenKind.EQUAL)

        rhs = self._parse_expression()

        return LocalBinding(
            name=name,
            parameters=tuple(parameters),
            rhs=rhs,
            span=self._span_from(start),
        )

    def _parse_let(self) -> LetExpr:
        start = self._expect(TokenKind.LET)

        self._expect(TokenKind.LBRACE)

        bindings = [self._parse_local_binding()]

        while self._match(TokenKind.SEMICOLON):
            bindings.append(self._parse_local_binding())

        self._expect(TokenKind.RBRACE)
        self._expect(TokenKind.IN)

        body = self._parse_expression()

        return LetExpr(
            bindings=tuple(bindings),
            body=body,
            span=self._span_from(start),
        )

    def _parse_pattern(self) -> Pattern:
        token = self._peek()

        if token.kind == TokenKind.IDENT:
            self._advance()

            return VarPattern(
                name=token.lexeme,
                span=token.span,
            )

        if token.kind == TokenKind.LBRACKET:
            start = self._advance()
            self._expect(TokenKind.RBRACKET)

            return NilPattern(
                span=self._span_from(start),
            )

        if token.kind == TokenKind.LPAREN:
            start = self._advance()

            head = self._expect(TokenKind.IDENT)
            self._expect(TokenKind.COLON)
            tail = self._expect(TokenKind.IDENT)

            self._expect(TokenKind.RPAREN)

            return ConsPattern(
                head=VarPattern(
                    name=head.lexeme,
                    span=head.span,
                ),
                tail=VarPattern(
                    name=tail.lexeme,
                    span=tail.span,
                ),
                span=self._span_from(start),
            )

        raise ParserError(
            f"Expected a pattern, found {token.kind.name}",
            token,
        )

    def _parse_definition(self) -> ValueDefinition | FunctionEquation:
        start = self._expect(TokenKind.IDENT)
        name = start.lexeme

        parameters: list[Pattern] = []

        while self._peek().kind in {
            TokenKind.IDENT,
            TokenKind.LBRACKET,
            TokenKind.LPAREN,
        }:
            parameters.append(self._parse_pattern())

        self._expect(TokenKind.EQUAL)

        rhs = self._parse_expression()

        if not parameters:
            return ValueDefinition(
                name=name,
                rhs=rhs,
                span=self._span_from(start),
            )

        return FunctionEquation(
            name=name,
            parameters=tuple(parameters),
            rhs=rhs,
            span=self._span_from(start),
        )

    def _parse_expression(self) -> Expr:
        kind = self._peek().kind

        if kind == TokenKind.LET:
            return self._parse_let()

        if kind == TokenKind.IF:
            return self._parse_if()

        if kind == TokenKind.BACKSLASH:
            return self._parse_lambda()

        return self._parse_comparison()

    def parse_expression(self) -> Expr:
        expression = self._parse_expression()
        self._expect(TokenKind.EOF)
        return expression

    def parse_program(self) -> Program:
        # Ignore leading blank lines.
        while self._match(TokenKind.NEWLINE):
            pass

        start = self._peek()
        definitions = []

        while self._peek().kind != TokenKind.EOF:
            definitions.append(self._parse_definition())

            if self._peek().kind != TokenKind.EOF:
                self._expect(TokenKind.NEWLINE)

                # Ignore blank lines between definitions.
                while self._match(TokenKind.NEWLINE):
                    pass

        self._expect(TokenKind.EOF)

        if not definitions:
            return Program(definitions=())

        last_span = definitions[-1].span

        return Program(
            definitions=tuple(definitions),
            span=SourceSpan(
                start_line=start.span.start_line,
                start_column=start.span.start_column,
                end_line=last_span.end_line,
                end_column=last_span.end_column,
            ),
        )

def _decimal_to_int(lexeme: str) -> int:
    value = 0
    block_size = 256

    for i in range(0, len(lexeme), block_size):
        block = lexeme[i:i + block_size]

        value = (
            value * (10 ** len(block))
            + int(block)
        )

    return value

def parse_expression(source: str) -> Expr:
    """Tokenize source and parse one complete expression."""
    tokens = tokenize(source)
    parser = _Parser(tokens)
    return parser.parse_expression()

def parse_program(source: str) -> Program:
    tokens = tokenize(source)
    parser = _Parser(tokens)
    return parser.parse_program()
