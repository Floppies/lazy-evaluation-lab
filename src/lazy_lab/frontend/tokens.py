from enum import Enum, auto
from dataclasses import dataclass

from ..source import SourceSpan


class TokenKind(Enum):
    # Identifiers and literals
    IDENT = auto()
    INT = auto()
    TRUE = auto()
    FALSE = auto()

    # Keywords
    IF = auto()
    THEN = auto()
    ELSE = auto()
    LET = auto()
    IN = auto()

    # Arithmetic
    PLUS = auto()
    MINUS = auto()
    STAR = auto()

    # Comparisons
    LT = auto()
    LTE = auto()
    GT = auto()
    GTE = auto()
    EQEQ = auto()
    NEQ = auto()

    # Language operators
    EQUAL = auto()
    ARROW = auto()
    BACKSLASH = auto()
    COLON = auto()

    # Delimiters
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    LBRACE = auto()
    RBRACE = auto()
    SEMICOLON = auto()
    COMMA = auto()

    # Control
    NEWLINE = auto()
    EOF = auto()

@dataclass(frozen=True, slots=True)
class Token:
    kind: TokenKind
    lexeme: str
    span: SourceSpan