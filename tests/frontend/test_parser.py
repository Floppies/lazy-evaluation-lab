import pytest

from lazy_lab.ast.nodes import (
    IntLiteral,
    BoolLiteral,
    Var,
    SourceSpan,
)
from lazy_lab.frontend.parser import parse_expression
from lazy_lab.frontend.errors import ParserError


@pytest.mark.parametrize(
    "source,expected",
    [
        ("42", IntLiteral(42)),
        ("0", IntLiteral(0)),
        ("True", BoolLiteral(True)),
        ("False", BoolLiteral(False)),
        ("x", Var("x")),
        ("main", Var("main")),
        ("(42)", IntLiteral(42)),
        ("((x))", Var("x")),
    ],
)
def test_atomic_expressions(source, expected):
    result = parse_expression(source)

    assert result == expected


def test_literal_source_span():
    expression = parse_expression("42")

    assert expression.span == SourceSpan(1, 1, 1, 3)


def test_parentheses_do_not_create_ast_node():
    expression = parse_expression("(42)")

    assert expression == IntLiteral(42)
    assert expression.span == SourceSpan(1, 2, 1, 4)


def test_missing_closing_parenthesis():
    with pytest.raises(ParserError) as error:
        parse_expression("(42")

    assert error.value.line == 1
    assert error.value.column == 4
    assert "Expected RPAREN" in str(error.value)


def test_unexpected_closing_parenthesis():
    with pytest.raises(ParserError, match="Expected EOF"):
        parse_expression("42)")


def test_empty_expression():
    with pytest.raises(ParserError, match="Expected an expression"):
        parse_expression("")


def test_incomplete_expression():
    with pytest.raises(ParserError):
        parse_expression("42 +")