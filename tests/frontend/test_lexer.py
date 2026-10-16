import pytest

from lazy_lab.frontend.errors import LexerError
from lazy_lab.frontend.lexer import Lexer, tokenize
from lazy_lab.frontend.tokens import Token, TokenKind
from lazy_lab.source import SourceSpan


def test_identifiers_and_integers():
    tokens = tokenize("double 10")

    assert tokens == (
        Token(TokenKind.IDENT, "double", SourceSpan(1, 1, 1, 7)),
        Token(TokenKind.INT, "10", SourceSpan(1, 8, 1, 10)),
        Token(TokenKind.EOF, "", SourceSpan(1, 10, 1, 10)),
    )


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
    assert [token.lexeme for token in tokens] == [
        "if", "then", "else", "let", "in", "True", "False", "",
    ]


@pytest.mark.parametrize(
    "name", ["ifx", "then1", "else_", "letdown", "inside", "trueValue", "falseValue"]
)
def test_keyword_prefix_is_identifier(name):
    end = len(name) + 1
    assert tokenize(name) == (
        Token(TokenKind.IDENT, name, SourceSpan(1, 1, 1, end)),
        Token(TokenKind.EOF, "", SourceSpan(1, end, 1, end)),
    )


def test_newline_positions():
    tokens = tokenize("abc 12\nFalse")

    assert tokens == (
        Token(TokenKind.IDENT, "abc", SourceSpan(1, 1, 1, 4)),
        Token(TokenKind.INT, "12", SourceSpan(1, 5, 1, 7)),
        Token(TokenKind.NEWLINE, "\n", SourceSpan(1, 7, 2, 1)),
        Token(TokenKind.FALSE, "False", SourceSpan(2, 1, 2, 6)),
        Token(TokenKind.EOF, "", SourceSpan(2, 6, 2, 6)),
    )


def test_crlf():
    tokens = tokenize("abc\r\n12")

    assert tokens == (
        Token(TokenKind.IDENT, "abc", SourceSpan(1, 1, 1, 4)),
        Token(TokenKind.NEWLINE, "\n", SourceSpan(1, 4, 2, 1)),
        Token(TokenKind.INT, "12", SourceSpan(2, 1, 2, 3)),
        Token(TokenKind.EOF, "", SourceSpan(2, 3, 2, 3)),
    )


def test_empty_source():
    tokens = tokenize("")

    assert tokens == (Token(TokenKind.EOF, "", SourceSpan(1, 1, 1, 1)),)


@pytest.mark.parametrize("source", ["T", "F", "Test", "TrueValue", "FalseValue", "False0"])
def test_invalid_identifiers(source):
    with pytest.raises(LexerError, match="Invalid identifier") as error:
        tokenize(source)
    assert (error.value.line, error.value.column) == (1, 1)
    assert str(error.value).startswith("1:1: ")


@pytest.mark.parametrize(
    "source,column",
    [("123abc", 4), ("123_", 4), ("123True", 4), ("123Z", 4), ("1_000", 2)],
)
def test_invalid_integer_suffix(source, column):
    with pytest.raises(LexerError, match="Invalid suffix") as error:
        tokenize(source)
    assert (error.value.line, error.value.column) == (1, column)
    assert str(error.value).startswith(f"1:{column}: ")


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

    end = len(lexeme) + 1
    assert tokens == (
        Token(expected_kind, lexeme, SourceSpan(1, 1, 1, end)),
        Token(TokenKind.EOF, "", SourceSpan(1, end, 1, end)),
    )


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
    [
        pytest.param("@", id="at"),
        pytest.param("!", id="bare-exclamation"),
        pytest.param("&", id="ampersand"),
        pytest.param("|", id="pipe"),
        pytest.param("/", id="division"),
        pytest.param("\u00e9", id="non-ascii-letter"),
        pytest.param("_x", id="underscore-start"),
        pytest.param("A", id="uppercase-start"),
        pytest.param("\u0661", id="arabic-indic-digit"),
        pytest.param("\uff11", id="fullwidth-digit"),
        pytest.param("\u00a0", id="nonbreaking-space"),
        pytest.param("\v", id="vertical-tab"),
        pytest.param("\f", id="form-feed"),
        pytest.param('"', id="string-delimiter"),
        pytest.param(".", id="decimal-point"),
    ],
)
def test_invalid_characters(source):
    with pytest.raises(LexerError, match="Unexpected character") as error:
        tokenize(source)
    assert (error.value.line, error.value.column) == (1, 1)
    assert str(error.value).startswith("1:1: ")


def test_token_positions():
    tokens = tokenize("x = 10\nmain = x")

    assert tokens[0].span == SourceSpan(1, 1, 1, 2)
    assert tokens[1].span == SourceSpan(1, 3, 1, 4)
    assert tokens[2].span == SourceSpan(1, 5, 1, 7)

    assert tokens[3].span == SourceSpan(1, 7, 2, 1)

    assert tokens[4].span == SourceSpan(2, 1, 2, 5)
    assert tokens[5].span == SourceSpan(2, 6, 2, 7)
    assert tokens[6].span == SourceSpan(2, 8, 2, 9)
    assert len(tokens) == 8
    assert tokens[7] == Token(TokenKind.EOF, "", SourceSpan(2, 9, 2, 9))


@pytest.mark.parametrize(
    "source",
    [
        "x\ny",
        "x\r\ny",
    ],
)
def test_line_endings(source):
    tokens = tokenize(source)

    assert tokens == (
        Token(TokenKind.IDENT, "x", SourceSpan(1, 1, 1, 2)),
        Token(TokenKind.NEWLINE, "\n", SourceSpan(1, 2, 2, 1)),
        Token(TokenKind.IDENT, "y", SourceSpan(2, 1, 2, 2)),
        Token(TokenKind.EOF, "", SourceSpan(2, 2, 2, 2)),
    )


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

    assert tokens == (
        Token(TokenKind.IDENT, "x", SourceSpan(1, 1, 1, 2)),
        Token(TokenKind.NEWLINE, "\n", SourceSpan(1, 13, 2, 1)),
        Token(TokenKind.IDENT, "y", SourceSpan(2, 1, 2, 2)),
        Token(TokenKind.EOF, "", SourceSpan(2, 2, 2, 2)),
    )


@pytest.mark.parametrize(
    "source,line,column",
    [
        pytest.param("x\ry", 1, 2, id="middle-of-source"),
        pytest.param("x\r", 1, 2, id="end-of-source"),
        pytest.param("-- comment\r", 1, 11, id="after-comment"),
        pytest.param("x\r\ny\r", 2, 2, id="after-crlf"),
    ],
)
def test_unsupported_line_ending(source, line, column):
    with pytest.raises(
        LexerError,
        match="Unsupported line ending",
    ) as error:
        tokenize(source)
    assert (error.value.line, error.value.column) == (line, column)
    assert str(error.value).startswith(f"{line}:{column}: ")


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

    assert first == (
        Token(TokenKind.IDENT, "x", SourceSpan(1, 1, 1, 2)),
        Token(TokenKind.EQUAL, "=", SourceSpan(1, 3, 1, 4)),
        Token(TokenKind.INT, "10", SourceSpan(1, 5, 1, 7)),
        Token(TokenKind.EOF, "", SourceSpan(1, 7, 1, 7)),
    )
    assert second == (
        Token(TokenKind.IDENT, "y", SourceSpan(1, 1, 1, 2)),
        Token(TokenKind.EQUAL, "=", SourceSpan(1, 3, 1, 4)),
        Token(TokenKind.INT, "20", SourceSpan(1, 5, 1, 7)),
        Token(TokenKind.EOF, "", SourceSpan(1, 7, 1, 7)),
    )


@pytest.mark.parametrize("entry_point", [Lexer, tokenize], ids=["constructor", "wrapper"])
@pytest.mark.parametrize(
    "source", [None, 1, True, b"x", []], ids=["none", "integer", "boolean", "bytes", "list"]
)
def test_source_must_be_a_string(entry_point, source):
    with pytest.raises(TypeError, match="Source must be a string"):
        entry_point(source)


@pytest.mark.parametrize("source", ["", "x", "x\n", "-- comment"])
def test_lexer_instance_cannot_be_used_twice(source):
    lexer = Lexer(source)
    first = lexer.tokenize()

    for _ in range(2):
        with pytest.raises(RuntimeError, match="only be called once.*new Lexer"):
            lexer.tokenize()

    assert sum(token.kind == TokenKind.EOF for token in first) == 1
    assert sum(token.kind == TokenKind.EOF for token in lexer.tokens) == 1


@pytest.mark.parametrize("source", ["@", "TrueValue", "123_"])
def test_failed_lexer_instance_cannot_be_reused(source):
    lexer = Lexer(source)

    with pytest.raises(LexerError):
        lexer.tokenize()
    with pytest.raises(RuntimeError, match="only be called once.*new Lexer"):
        lexer.tokenize()


@pytest.mark.parametrize(
    "source,line,column",
    [
        pytest.param("", 1, 1, id="empty"),
        pytest.param(" \t ", 1, 4, id="whitespace-only"),
        pytest.param("\t\t", 1, 3, id="tabs-only"),
        pytest.param("-- comment", 1, 11, id="comment-only"),
        pytest.param("\n", 2, 1, id="lf-only"),
        pytest.param("\r\n", 2, 1, id="crlf-only"),
        pytest.param("x", 1, 2, id="no-final-newline"),
        pytest.param("x\n", 2, 1, id="final-lf"),
        pytest.param("x\r\n", 2, 1, id="final-crlf"),
        pytest.param("x \t", 1, 4, id="trailing-whitespace"),
        pytest.param("x -- final", 1, 11, id="trailing-comment"),
    ],
)
def test_output_is_a_token_tuple_with_one_final_eof(source, line, column):
    tokens = tokenize(source)

    assert isinstance(tokens, tuple)
    assert all(isinstance(token, Token) for token in tokens)
    assert sum(token.kind == TokenKind.EOF for token in tokens) == 1
    assert tokens[-1] == Token(TokenKind.EOF, "", SourceSpan(line, column, line, column))
    for token in tokens[:-1]:
        assert (token.span.start_line, token.span.start_column) < (
            token.span.end_line, token.span.end_column
        )


@pytest.mark.parametrize("source,column", [(" ", 2), ("\t", 2), (" \t ", 4)])
def test_horizontal_whitespace_only_produces_eof(source, column):
    assert tokenize(source) == (
        Token(TokenKind.EOF, "", SourceSpan(1, column, 1, column)),
    )


def test_tabs_count_as_one_source_column():
    assert tokenize(" \tx\t= 1 \t") == (
        Token(TokenKind.IDENT, "x", SourceSpan(1, 3, 1, 4)),
        Token(TokenKind.EQUAL, "=", SourceSpan(1, 5, 1, 6)),
        Token(TokenKind.INT, "1", SourceSpan(1, 7, 1, 8)),
        Token(TokenKind.EOF, "", SourceSpan(1, 10, 1, 10)),
    )


def test_tab_after_newline_advances_from_column_one():
    assert tokenize("x\n\ty") == (
        Token(TokenKind.IDENT, "x", SourceSpan(1, 1, 1, 2)),
        Token(TokenKind.NEWLINE, "\n", SourceSpan(1, 2, 2, 1)),
        Token(TokenKind.IDENT, "y", SourceSpan(2, 2, 2, 3)),
        Token(TokenKind.EOF, "", SourceSpan(2, 3, 2, 3)),
    )


@pytest.mark.parametrize("name", ["x", "xA_2", "a0", "a_", "true", "false", "main", "aZ09_"])
def test_valid_ascii_identifiers(name):
    end = len(name) + 1
    assert tokenize(name) == (
        Token(TokenKind.IDENT, name, SourceSpan(1, 1, 1, end)),
        Token(TokenKind.EOF, "", SourceSpan(1, end, 1, end)),
    )


@pytest.mark.parametrize(
    "digits",
    [
        pytest.param("0", id="zero"),
        pytest.param("000", id="all-zeroes"),
        pytest.param("00123", id="leading-zeroes"),
        pytest.param("9" * 5000, id="very-long-integer"),
    ],
)
def test_integer_lexemes_are_preserved_without_numeric_conversion(digits):
    end = len(digits) + 1
    assert tokenize(digits) == (
        Token(TokenKind.INT, digits, SourceSpan(1, 1, 1, end)),
        Token(TokenKind.EOF, "", SourceSpan(1, end, 1, end)),
    )


def test_negative_integer_is_a_minus_followed_by_an_unsigned_integer():
    assert tokenize("-3") == (
        Token(TokenKind.MINUS, "-", SourceSpan(1, 1, 1, 2)),
        Token(TokenKind.INT, "3", SourceSpan(1, 2, 1, 3)),
        Token(TokenKind.EOF, "", SourceSpan(1, 3, 1, 3)),
    )


@pytest.mark.parametrize(
    "source,expected",
    [
        pytest.param(
            "x==10",
            [(TokenKind.IDENT, "x"), (TokenKind.EQEQ, "=="), (TokenKind.INT, "10")],
            id="equality",
        ),
        pytest.param(
            "x<=10",
            [(TokenKind.IDENT, "x"), (TokenKind.LTE, "<="), (TokenKind.INT, "10")],
            id="less-or-equal",
        ),
        pytest.param(
            "x>=10",
            [(TokenKind.IDENT, "x"), (TokenKind.GTE, ">="), (TokenKind.INT, "10")],
            id="greater-or-equal",
        ),
        pytest.param(
            "x!=10",
            [(TokenKind.IDENT, "x"), (TokenKind.NEQ, "!="), (TokenKind.INT, "10")],
            id="not-equal",
        ),
        pytest.param(
            "x->y",
            [(TokenKind.IDENT, "x"), (TokenKind.ARROW, "->"), (TokenKind.IDENT, "y")],
            id="arrow",
        ),
        pytest.param(
            "x===y",
            [
                (TokenKind.IDENT, "x"), (TokenKind.EQEQ, "=="),
                (TokenKind.EQUAL, "="), (TokenKind.IDENT, "y"),
            ],
            id="maximal-munch-with-remainder",
        ),
    ],
)
def test_adjacent_tokens_use_maximal_munch(source, expected):
    assert [(token.kind, token.lexeme) for token in tokenize(source)] == [
        *expected, (TokenKind.EOF, ""),
    ]


@pytest.mark.parametrize("ending", ["", "\n", "\r\n"], ids=["eof", "lf", "crlf"])
@pytest.mark.parametrize(
    "content",
    [
        pytest.param("", id="bare-comment"),
        pytest.param("comment", id="text"),
        pytest.param(" @ ! / \u00e9 \u0661", id="otherwise-invalid-characters"),
        pytest.param('-- -> "\t', id="symbols-and-tab"),
    ],
)
def test_comment_only_source_ignores_contents_and_preserves_newline(content, ending):
    source = "--" + content + ending
    column = len("--" + content) + 1
    if ending:
        expected = (
            Token(TokenKind.NEWLINE, "\n", SourceSpan(1, column, 2, 1)),
            Token(TokenKind.EOF, "", SourceSpan(2, 1, 2, 1)),
        )
    else:
        expected = (Token(TokenKind.EOF, "", SourceSpan(1, column, 1, column)),)

    assert tokenize(source) == expected


@pytest.mark.parametrize("ending", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_inline_comment_preserves_following_token_location(ending):
    assert tokenize("x -- @\u00e9" + ending + "y") == (
        Token(TokenKind.IDENT, "x", SourceSpan(1, 1, 1, 2)),
        Token(TokenKind.NEWLINE, "\n", SourceSpan(1, 8, 2, 1)),
        Token(TokenKind.IDENT, "y", SourceSpan(2, 1, 2, 2)),
        Token(TokenKind.EOF, "", SourceSpan(2, 2, 2, 2)),
    )


def test_mixed_line_endings_and_consecutive_blank_lines():
    assert tokenize("\n\r\nx\r\n\n") == (
        Token(TokenKind.NEWLINE, "\n", SourceSpan(1, 1, 2, 1)),
        Token(TokenKind.NEWLINE, "\n", SourceSpan(2, 1, 3, 1)),
        Token(TokenKind.IDENT, "x", SourceSpan(3, 1, 3, 2)),
        Token(TokenKind.NEWLINE, "\n", SourceSpan(3, 2, 4, 1)),
        Token(TokenKind.NEWLINE, "\n", SourceSpan(4, 1, 5, 1)),
        Token(TokenKind.EOF, "", SourceSpan(5, 1, 5, 1)),
    )


@pytest.mark.parametrize(
    "source,message,line,column",
    [
        pytest.param("\t@", "Unexpected character", 1, 2, id="after-tab"),
        pytest.param("x\r\n\t@", "Unexpected character", 2, 2, id="after-crlf"),
        pytest.param(
            "-- ignored\r\n\t@", "Unexpected character", 2, 2, id="after-comment"
        ),
        pytest.param(
            "x\r\n\tTrueValue", "Invalid identifier", 2, 2, id="uppercase-identifier"
        ),
        pytest.param(
            "x\r\n\t123abc", "Invalid suffix", 2, 5, id="integer-suffix"
        ),
        pytest.param("x\u00e9", "Unexpected character", 1, 2, id="non-ascii-suffix"),
        pytest.param("12\u0661", "Unexpected character", 1, 3, id="non-ascii-digit-suffix"),
    ],
)
def test_lexical_errors_report_source_character_locations(source, message, line, column):
    with pytest.raises(LexerError, match=message) as error:
        tokenize(source)

    assert (error.value.line, error.value.column) == (line, column)
    assert str(error.value).startswith(f"{line}:{column}: ")


@pytest.mark.parametrize(
    "source,expected",
    [
        pytest.param(
            "main = 1 +",
            [
                (TokenKind.IDENT, "main"), (TokenKind.EQUAL, "="),
                (TokenKind.INT, "1"), (TokenKind.PLUS, "+"),
            ],
            id="incomplete-expression",
        ),
        pytest.param("(", [(TokenKind.LPAREN, "(")], id="unmatched-parenthesis"),
        pytest.param(
            "x = 1 < 2 < 3",
            [
                (TokenKind.IDENT, "x"), (TokenKind.EQUAL, "="),
                (TokenKind.INT, "1"), (TokenKind.LT, "<"),
                (TokenKind.INT, "2"), (TokenKind.LT, "<"), (TokenKind.INT, "3"),
            ],
            id="chained-comparisons",
        ),
        pytest.param(
            "main x = x",
            [
                (TokenKind.IDENT, "main"), (TokenKind.IDENT, "x"),
                (TokenKind.EQUAL, "="), (TokenKind.IDENT, "x"),
            ],
            id="function-named-main",
        ),
    ],
)
def test_lexer_does_not_enforce_syntax_or_definition_rules(source, expected):
    assert [(token.kind, token.lexeme) for token in tokenize(source)] == [
        *expected, (TokenKind.EOF, ""),
    ]
