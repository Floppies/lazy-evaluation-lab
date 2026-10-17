import pytest

from lazy_lab.ast.nodes import (
    Expr,
    IntLiteral,
    BoolLiteral,
    Var,
    SourceSpan,
    UnaryOp,
    BinaryOp,
    Application,
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

"""Precedence and associativity"""

@pytest.mark.parametrize(
    "source, expected",
    [
        (
            "1 + 2 * 3",
            BinaryOp(
                "+",
                IntLiteral(1),
                BinaryOp("*", IntLiteral(2), IntLiteral(3)),
            ),
        ),
        (
            "(1 + 2) * 3",
            BinaryOp(
                "*",
                BinaryOp("+", IntLiteral(1), IntLiteral(2)),
                IntLiteral(3),
            ),
        ),
        (
            "10 - 3 - 2",
            BinaryOp(
                "-",
                BinaryOp("-", IntLiteral(10), IntLiteral(3)),
                IntLiteral(2),
            ),
        ),
        (
            "1 : 2 : xs",
            BinaryOp(
                ":",
                IntLiteral(1),
                BinaryOp(":", IntLiteral(2), Var("xs")),
            ),
        ),
        (
            "double 3 + 2",
            BinaryOp(
                "+",
                Application(Var("double"), IntLiteral(3)),
                IntLiteral(2),
            ),
        ),
    ],
)
def test_operator_precedence(source, expected):
    assert parse_expression(source) == expected

"""Application and negation"""

def test_left_associative_application():
    result = parse_expression("f x y")

    expected = Application(
        Application(Var("f"), Var("x")),
        Var("y"),
    )

    assert result == expected


def test_negative_argument_requires_parentheses():
    assert parse_expression("f (-3)") == Application(
        Var("f"),
        UnaryOp("-", IntLiteral(3)),
    )

    assert parse_expression("f - 3") == BinaryOp(
        "-",
        Var("f"),
        IntLiteral(3),
    )


def test_application_precedes_unary_negation():
    assert parse_expression("-f x") == UnaryOp(
        "-",
        Application(Var("f"), Var("x")),
    )

"""Comparisons"""

@pytest.mark.parametrize(
    "operator",
    ["==", "!=", "<", "<=", ">", ">="],
)
def test_comparison_operators(operator):
    result = parse_expression(f"1 {operator} 2")

    assert result == BinaryOp(
        operator,
        IntLiteral(1),
        IntLiteral(2),
    )


@pytest.mark.parametrize(
    "source",
    [
        "1 < 2 < 3",
        "1 == 2 != 3",
        "a >= b <= c",
    ],
)
def test_chained_comparisons_are_rejected(source):
    with pytest.raises(
        ParserError,
        match="Chained comparisons",
    ):
        parse_expression(source)

"""Spans for composed expressions"""

def test_application_span_includes_parentheses():
    result = parse_expression("f(2)")

    assert result == Application(
        Var("f"),
        IntLiteral(2),
    )

    assert result.span == SourceSpan(1, 1, 1, 5)


def test_binary_operation_span_includes_grouping():
    result = parse_expression("(1 + 2) * 3")

    assert result.span == SourceSpan(1, 1, 1, 12)
