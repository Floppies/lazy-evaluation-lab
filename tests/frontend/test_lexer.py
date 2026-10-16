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

def test_token_positions():
    tokens = tokenize("x = 10\nmain = x")

    assert tokens[0].span == SourceSpan(1, 1, 1, 2)
    assert tokens[1].span == SourceSpan(1, 3, 1, 4)
    assert tokens[2].span == SourceSpan(1, 5, 1, 7)

    assert tokens[3].span == SourceSpan(1, 7, 2, 1)

    assert tokens[4].span == SourceSpan(2, 1, 2, 5)
    assert tokens[5].span == SourceSpan(2, 6, 2, 7)
    assert tokens[6].span == SourceSpan(2, 8, 2, 9)

@pytest.mark.parametrize(
    "source",
    [
        "x\ny",
        "x\r\ny",
    ],
)
def test_line_endings(source):
    tokens = tokenize(source)

    assert tokens[0].span == SourceSpan(1, 1, 1, 2)
    assert tokens[1].kind == TokenKind.NEWLINE
    assert tokens[1].span == SourceSpan(1, 2, 2, 1)
    assert tokens[2].span == SourceSpan(2, 1, 2, 2)

def test_error_location():
    with pytest.raises(LexerError) as error:
        tokenize("x = 10\nmain @ 20")

    assert error.value.line == 2
    assert error.value.column == 6
    assert "Unexpected character" in str(error.value)

def test_invalid_integer_suffix_location():
    with pytest.raises(LexerError) as error:
        tokenize("n 123abc")

    assert error.value.line == 1
    assert error.value.column == 6
    assert "Invalid suffix" in str(error.value)

def test_eof_position_after_comment():
    tokens = tokenize("x -- comment")

    assert [token.kind for token in tokens] == [
        TokenKind.IDENT,
        TokenKind.EOF,
    ]

    assert tokens[-1].span == SourceSpan(1, 13, 1, 13)

def test_comment_preserves_next_line_position():
    tokens = tokenize("x -- comment\ny")

    assert tokens[2].kind == TokenKind.IDENT
    assert tokens[2].lexeme == "y"
    assert tokens[2].span == SourceSpan(2, 1, 2, 2)

def test_unsupported_line_ending():
    with pytest.raises(
        LexerError,
        match="Unsupported line ending",
    ):
        tokenize("x\ry")

def test_complex_expression():
    source = (
        r"main = let { double = \x -> x * 2 } "
        "in double(10) -- Result"
        "\n"
    )

    tokens = tokenize(source)

    expected = [
        (TokenKind.IDENT, "main"),
        (TokenKind.EQUAL, "="),
        (TokenKind.LET, "let"),
        (TokenKind.LBRACE, "{"),
        (TokenKind.IDENT, "double"),
        (TokenKind.EQUAL, "="),
        (TokenKind.BACKSLASH, "\\"),
        (TokenKind.IDENT, "x"),
        (TokenKind.ARROW, "->"),
        (TokenKind.IDENT, "x"),
        (TokenKind.STAR, "*"),
        (TokenKind.INT, "2"),
        (TokenKind.RBRACE, "}"),
        (TokenKind.IN, "in"),
        (TokenKind.IDENT, "double"),
        (TokenKind.LPAREN, "("),
        (TokenKind.INT, "10"),
        (TokenKind.RPAREN, ")"),
        (TokenKind.NEWLINE, "\n"),
        (TokenKind.EOF, ""),
    ]

    assert [(token.kind, token.lexeme) for token in tokens] == expected

def test_pattern_matching_program():
    source = (
        "map f [] = []\n"
        "map f (x:xs) = f x : map f xs\n"
    )

    tokens = tokenize(source)

    expected_kinds = [
        # map f [] = []
        TokenKind.IDENT,
        TokenKind.IDENT,
        TokenKind.LBRACKET,
        TokenKind.RBRACKET,
        TokenKind.EQUAL,
        TokenKind.LBRACKET,
        TokenKind.RBRACKET,
        TokenKind.NEWLINE,

        # map f (x:xs) = f x : map f xs
        TokenKind.IDENT,
        TokenKind.IDENT,
        TokenKind.LPAREN,
        TokenKind.IDENT,
        TokenKind.COLON,
        TokenKind.IDENT,
        TokenKind.RPAREN,
        TokenKind.EQUAL,
        TokenKind.IDENT,
        TokenKind.IDENT,
        TokenKind.COLON,
        TokenKind.IDENT,
        TokenKind.IDENT,
        TokenKind.IDENT,
        TokenKind.NEWLINE,

        TokenKind.EOF,
    ]

    assert [token.kind for token in tokens] == expected_kinds

def test_blank_lines_and_comment_only_lines():
    source = (
        "f [] = []\n"
        "\n"
        "-- Another equation\n"
        "f (x:xs) = x\n"
    )

    tokens = tokenize(source)

    assert sum(
        token.kind == TokenKind.NEWLINE
        for token in tokens
    ) == 4

    assert [
        token.lexeme
        for token in tokens
        if token.kind == TokenKind.IDENT
    ] == ["f", "f", "x", "xs", "x"]

def test_line_ending_normalization():
    source_lf = "x = 1\ny = 2"
    source_crlf = "x = 1\r\ny = 2"

    assert tokenize(source_lf) == tokenize(source_crlf)

def test_independent_tokenize_calls():
    first = tokenize("x = 10")
    second = tokenize("y = 20")

    assert first[0].lexeme == "x"
    assert second[0].lexeme == "y"

    assert first[0].span == SourceSpan(1, 1, 1, 2)
    assert second[0].span == SourceSpan(1, 1, 1, 2)