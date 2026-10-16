from __future__ import annotations

from ..source import SourceSpan
from .tokens import Token, TokenKind
from .errors import LexerError


_KEYWORDS = {
    "if": TokenKind.IF,
    "then": TokenKind.THEN,
    "else": TokenKind.ELSE,
    "let": TokenKind.LET,
    "in": TokenKind.IN,
    "True": TokenKind.TRUE,
    "False": TokenKind.FALSE,
}

_TWO_CHAR_TOKENS = {
    "->": TokenKind.ARROW,
    "<=": TokenKind.LTE,
    ">=": TokenKind.GTE,
    "==": TokenKind.EQEQ,
    "!=": TokenKind.NEQ,
}

_ONE_CHAR_TOKENS = {
    "+": TokenKind.PLUS,
    "-": TokenKind.MINUS,
    "*": TokenKind.STAR,
    "<": TokenKind.LT,
    ">": TokenKind.GT,
    "=": TokenKind.EQUAL,
    "\\": TokenKind.BACKSLASH,
    ":": TokenKind.COLON,
    "(": TokenKind.LPAREN,
    ")": TokenKind.RPAREN,
    "[": TokenKind.LBRACKET,
    "]": TokenKind.RBRACKET,
    "{": TokenKind.LBRACE,
    "}": TokenKind.RBRACE,
    ";": TokenKind.SEMICOLON,
    ",": TokenKind.COMMA,
}


def _is_identifier_start(char: str) -> bool:
    return "a" <= char <= "z" or char in ("T", "F")


def _is_identifier_part(char: str) -> bool:
    return (
        "a" <= char <= "z"
        or "A" <= char <= "Z"
        or "0" <= char <= "9"
        or char == "_"
    )


def _is_digit(char: str) -> bool:
    return "0" <= char <= "9"


class Lexer:
    """Scan a fixed source string once.

    Columns count source characters: a horizontal tab advances one column.
    """

    def __init__(self, source: str):
        if not isinstance(source, str):
            raise TypeError("Source must be a string")

        self.source = source
        self.index = 0
        self.line = 1
        self.column = 1
        self.tokens: list[Token] = []
        self._tokenize_called = False

    def _peek(self) -> str:
        if self.index >= len(self.source):
            return ""
        return self.source[self.index]

    def _advance(self) -> str:
        char = self.source[self.index]
        self.index += 1
        self.column += 1
        return char

    def _emit(
        self,
        kind: TokenKind,
        lexeme: str,
        start_line: int,
        start_column: int
    ) -> None:
        self.tokens.append(
            Token(
                kind=kind,
                lexeme=lexeme,
                span=SourceSpan(
                    start_line,
                    start_column,
                    self.line,
                    self.column
                )
            )
        )

    def _scan_identifier(self) -> None:
        start_index = self.index
        start_line = self.line
        start_column = self.column

        while _is_identifier_part(self._peek()):
            self._advance()

        lexeme = self.source[start_index:self.index]

        if lexeme in _KEYWORDS:
            kind = _KEYWORDS[lexeme]
        elif "a" <= lexeme[0] <= "z":
            kind = TokenKind.IDENT
        else:
            raise LexerError(
                f"Invalid identifier: {lexeme!r}",
                start_line,
                start_column
            )

        self._emit(kind, lexeme, start_line, start_column)

    def _scan_integer(self) -> None:
        start_index = self.index
        start_line = self.line
        start_column = self.column

        while _is_digit(self._peek()):
            self._advance()

        if _is_identifier_part(self._peek()):
            raise LexerError(
                "Invalid suffix after integer literal",
                self.line,
                self.column
            )

        lexeme = self.source[start_index:self.index]
        self._emit(TokenKind.INT, lexeme, start_line, start_column)

    def _scan_newline(self) -> None:
        start_line = self.line
        start_column = self.column

        if self._peek() == "\r":
            if self.index + 1 >= len(self.source) or self.source[self.index + 1] != "\n":
                raise LexerError("Unsupported line ending", self.line, self.column)
            self.index += 2
        else:
            self.index += 1

        self.line += 1
        self.column = 1

        self._emit(TokenKind.NEWLINE, "\n", start_line, start_column)

    def _scan_symbol(self, length: int) -> None:
        start_line = self.line
        start_column = self.column

        lexeme = self.source[self.index:self.index + length]

        if length == 2:
            kind = _TWO_CHAR_TOKENS[lexeme]
        else:
            kind = _ONE_CHAR_TOKENS[lexeme]

        for _ in range(length):
            self._advance()

        self._emit(kind, lexeme, start_line, start_column)

    def _skip_comment(self) -> None:
        while self._peek() not in ("", "\n", "\r"):
            self._advance()

    def tokenize(self) -> tuple[Token, ...]:
        """Return a token tuple with exactly one final EOF.

        Reusing the scanner, even after a lexical error, raises RuntimeError.
        """
        if self._tokenize_called:
            raise RuntimeError(
                "Lexer.tokenize() can only be called once; create a new Lexer to scan again"
            )
        self._tokenize_called = True
        return self._scan_tokens()

    def _scan_tokens(self) -> tuple[Token, ...]:
        while self.index < len(self.source):
            char = self._peek()

            if char in (" ", "\t"):
                self._advance()

            elif char in ("\n", "\r"):
                self._scan_newline()

            elif _is_identifier_start(char):
                self._scan_identifier()

            elif _is_digit(char):
                self._scan_integer()

            elif self.source.startswith("--", self.index):
                self._skip_comment()

            elif self.source[self.index:self.index + 2] in _TWO_CHAR_TOKENS:
                self._scan_symbol(2)

            elif char in _ONE_CHAR_TOKENS:
                self._scan_symbol(1)

            else:
                raise LexerError(
                    f"Unexpected character: {char!r}",
                    self.line,
                    self.column
                )

        self.tokens.append(
            Token(
                kind=TokenKind.EOF,
                lexeme="",
                span=SourceSpan(
                    self.line,
                    self.column,
                    self.line,
                    self.column
                )
            )
        )

        return tuple(self.tokens)


def tokenize(source: str) -> tuple[Token, ...]:
    """Tokenize source without parsing or resolving names."""
    return Lexer(source).tokenize()
