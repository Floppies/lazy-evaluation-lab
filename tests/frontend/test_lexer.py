import pytest

from lazy_lab.frontend.lexer import tokenize
from lazy_lab.frontend.tokens import Token, TokenKind
from lazy_lab.frontend.errors import LexerError
from lazy_lab.source import SourceSpan

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

@pytest.mark.parametrize(
    "lexeme, expected_kind",
    [
        ("+", TokenKind.PLUS),
        ("-", TokenKind.MINUS),
        ("*", TokenKind.STAR),
        ("<", TokenKind.LT),
        ("<=", TokenKind.LTE),
        (">", TokenKind.GT),
        (">=", TokenKind.GTE),
        ("=", TokenKind.EQUAL),
        ("==", TokenKind.EQEQ),
        ("!=", TokenKind.NEQ),
        ("->", TokenKind.ARROW),
        (":", TokenKind.COLON),
        ("\\", TokenKind.BACKSLASH),
        ("(", TokenKind.LPAREN),
        (")", TokenKind.RPAREN),
        ("[", TokenKind.LBRACKET),
        ("]", TokenKind.RBRACKET),
        ("{", TokenKind.LBRACE),
        ("}", TokenKind.RBRACE),
        (";", TokenKind.SEMICOLON),
        (",", TokenKind.COMMA),
    ],
)
def test_symbols(lexeme, expected_kind):
    tokens = tokenize(lexeme)

    assert tokens[0].kind == expected_kind
    assert tokens[0].lexeme == lexeme
    assert tokens[0].span == SourceSpan(
        1, 1, 1, len(lexeme) + 1
    )
    assert tokens[1].kind == TokenKind.EOF

def test_comments():
    tokens = tokenize("x -- comment\ny")

    assert [token.kind for token in tokens] == [
        TokenKind.IDENT,
        TokenKind.NEWLINE,
        TokenKind.IDENT,
        TokenKind.EOF,
    ]


def test_comment_at_eof():
    tokens = tokenize("x -- final comment")

    assert [token.kind for token in tokens] == [
        TokenKind.IDENT,
        TokenKind.EOF,
    ]


def test_adjacent_minuses_start_comment():
    tokens = tokenize("10--2")

    assert [token.kind for token in tokens] == [
        TokenKind.INT,
        TokenKind.EOF,
    ]


def test_separated_minuses():
    tokens = tokenize("10 - -2")

    assert [token.kind for token in tokens] == [
        TokenKind.INT,
        TokenKind.MINUS,
        TokenKind.MINUS,
        TokenKind.INT,
        TokenKind.EOF,
    ]

def test_complete_program():
    source = (
        "double x = x * 2\n"
        "main = double(10)\n"
    )

    tokens = tokenize(source)

    assert [token.kind for token in tokens] == [
        TokenKind.IDENT,
        TokenKind.IDENT,
        TokenKind.EQUAL,
        TokenKind.IDENT,
        TokenKind.STAR,
        TokenKind.INT,
        TokenKind.NEWLINE,
        TokenKind.IDENT,
        TokenKind.EQUAL,
        TokenKind.IDENT,
        TokenKind.LPAREN,
        TokenKind.INT,
        TokenKind.RPAREN,
        TokenKind.NEWLINE,
        TokenKind.EOF,
    ]

@pytest.mark.parametrize(
    "source",
    ["@", "!", "&", "|", "/", "é"],
)
def test_invalid_characters(source):
    with pytest.raises(LexerError):
        tokenize(source)