from dataclasses import FrozenInstanceError, replace

import pytest

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
    assert hash(a) == hash(b)


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"kind": TokenKind.IDENT}, id="kind"),
        pytest.param({"lexeme": "43"}, id="lexeme"),
        pytest.param({"span": SourceSpan(2, 1, 2, 3)}, id="span"),
    ],
)
def test_token_equality_includes_every_field(changes):
    token = Token(TokenKind.INT, "42", SourceSpan(1, 1, 1, 3))

    assert token != replace(token, **changes)


@pytest.mark.parametrize(
    "field,value",
    [
        pytest.param("kind", TokenKind.INT, id="kind"),
        pytest.param("lexeme", "other", id="lexeme"),
        pytest.param("span", SourceSpan(2, 1, 2, 5), id="span"),
    ],
)
def test_tokens_are_immutable(field, value):
    token = Token(TokenKind.IDENT, "main", SourceSpan(1, 1, 1, 5))

    with pytest.raises(FrozenInstanceError):
        setattr(token, field, value)


def test_token_span_is_immutable():
    token = Token(TokenKind.IDENT, "main", SourceSpan(1, 1, 1, 5))

    with pytest.raises(FrozenInstanceError):
        token.span.start_column = 2
