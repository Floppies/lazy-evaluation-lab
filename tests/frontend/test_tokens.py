from lazy_lab.frontend.tokens import Token, TokenKind
from lazy_lab.source import SourceSpan


def test_token_creation():
    token = Token(
        kind=TokenKind.IDENT,
        lexeme="main",
        span=SourceSpan(1, 1, 1, 5)
    )

    assert token.kind == TokenKind.IDENT
    assert token.lexeme == "main"
    assert token.span.start_column == 1
    assert token.span.end_column == 5


def test_token_equality():
    span = SourceSpan(1, 1, 1, 3)

    a = Token(TokenKind.INT, "42", span)
    b = Token(TokenKind.INT, "42", span)

    assert a == b