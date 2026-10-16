import pytest

from lazy_lab.frontend.lexer import tokenize
from lazy_lab.frontend.tokens import Token, TokenKind
from lazy_lab.frontend.errors import LexerError
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

def test_identifiers_and_integers():
    tokens = tokenize("double 10")

    assert [token.kind for token in tokens] == [
        TokenKind.IDENT,
        TokenKind.INT,
        TokenKind.EOF,
    ]

    assert tokens[0].lexeme == "double"
    assert tokens[1].lexeme == "10"


def test_keywords():
    tokens = tokenize("if then else let in True False")

    assert [token.kind for token in tokens] == [
        TokenKind.IF,
        TokenKind.THEN,
        TokenKind.ELSE,
        TokenKind.LET,
        TokenKind.IN,
        TokenKind.TRUE,
        TokenKind.FALSE,
        TokenKind.EOF,
    ]


def test_keyword_prefix_is_identifier():
    tokens = tokenize("ifx trueValue")

    assert tokens[0].kind == TokenKind.IDENT
    assert tokens[1].kind == TokenKind.IDENT


def test_newline_positions():
    tokens = tokenize("abc 12\nFalse")

    assert tokens[0].span == SourceSpan(1, 1, 1, 4)
    assert tokens[1].span == SourceSpan(1, 5, 1, 7)
    assert tokens[2].span == SourceSpan(1, 7, 2, 1)
    assert tokens[3].span == SourceSpan(2, 1, 2, 6)
    assert tokens[4].span == SourceSpan(2, 6, 2, 6)


def test_crlf():
    tokens = tokenize("abc\r\n12")

    assert tokens[1].kind == TokenKind.NEWLINE
    assert tokens[2].span == SourceSpan(2, 1, 2, 3)


def test_empty_source():
    tokens = tokenize("")

    assert len(tokens) == 1
    assert tokens[0].kind == TokenKind.EOF


@pytest.mark.parametrize("source", ["Test", "FalseValue", "é"])
def test_invalid_identifiers(source):
    with pytest.raises(LexerError):
        tokenize(source)


def test_invalid_integer_suffix():
    with pytest.raises(LexerError, match="Invalid suffix"):
        tokenize("123abc")