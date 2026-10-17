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
    LambdaExpr,
    IfExpr,
    LetExpr,
    LocalBinding,
    ListLiteral
)
from lazy_lab.frontend.parser import parse_expression
from lazy_lab.frontend.errors import ParserError
from lazy_lab.ast.validation import validate_expression


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

"""List"""

@pytest.mark.parametrize(
    "source, expected",
    [
        ("[]", ListLiteral(())),
        ("[1]", ListLiteral((IntLiteral(1),))),
        (
            "[1, 2 + 3]",
            ListLiteral((
                IntLiteral(1),
                BinaryOp("+", IntLiteral(2), IntLiteral(3)),
            )),
        ),
        (
            "f [1, 2]",
            Application(
                Var("f"),
                ListLiteral((IntLiteral(1), IntLiteral(2))),
            ),
        ),
    ],
)
def test_list_expressions(source, expected):
    assert parse_expression(source) == expected


def test_list_span_includes_brackets():
    source = "[1, 2]"
    result = parse_expression(source)

    assert result.span == SourceSpan(1, 1, 1, len(source) + 1)

"""Lambdas"""

def test_lambda_expression():
    result = parse_expression(r"\x y -> x + y")

    expected = LambdaExpr(
        parameters=("x", "y"),
        body=BinaryOp("+", Var("x"), Var("y")),
    )

    assert result == expected


def test_lambda_as_function_argument():
    result = parse_expression(r"map (\x -> x * 2) xs")

    expected = Application(
        Application(
            Var("map"),
            LambdaExpr(
                ("x",),
                BinaryOp("*", Var("x"), IntLiteral(2)),
            ),
        ),
        Var("xs"),
    )

    assert result == expected

"""Conditionals"""

def test_if_expression():
    result = parse_expression("if x == 0 then 1 else x + 2")

    expected = IfExpr(
        condition=BinaryOp("==", Var("x"), IntLiteral(0)),
        then_branch=IntLiteral(1),
        else_branch=BinaryOp("+", Var("x"), IntLiteral(2)),
    )

    assert result == expected


def test_nested_if():
    result = parse_expression(
        "if a then if b then 1 else 2 else 3"
    )

    expected = IfExpr(
        Var("a"),
        IfExpr(
            Var("b"),
            IntLiteral(1),
            IntLiteral(2),
        ),
        IntLiteral(3),
    )

    assert result == expected

"""Local Bindings"""

def test_let_expression():
    result = parse_expression(
        "let { x = 10; double y = y * 2 } in double x"
    )

    expected = LetExpr(
        bindings=(
            LocalBinding("x", (), IntLiteral(10)),
            LocalBinding(
                "double",
                ("y",),
                BinaryOp("*", Var("y"), IntLiteral(2)),
            ),
        ),
        body=Application(Var("double"), Var("x")),
    )

    assert result == expected


def test_mutually_recursive_let():
    result = parse_expression(
        "let { f x = g x; g x = f x } in f 10"
    )

    assert isinstance(result, LetExpr)
    assert len(result.bindings) == 2
    assert result.bindings[0].name == "f"
    assert result.bindings[1].name == "g"

"""Syntax errors"""

@pytest.mark.parametrize(
    "source",
    [
        "[1, 2",
        "[1,]",
        r"\ -> 10",
        r"\x 10",
        "if True then 1",
        "if True 1 else 2",
        "let {} in 1",
        "let { x = 1; } in x",
        "let { x = 1 } x",
    ],
)
def test_invalid_complex_expressions(source):
    with pytest.raises(ParserError):
        parse_expression(source)

"""Parser does not semantic validation"""

def test_parser_does_not_reject_recursive_binding():
    result = parse_expression("let { x = x } in x")

    assert isinstance(result, LetExpr)

"""Complex expressions"""

def test_complex_expression_combination():
    source = (
        r"let { double = \x -> x * 2 } "
        "in if True then double [1, 2] else []"
    )

    result = parse_expression(source)

    assert isinstance(result, LetExpr)
    assert isinstance(result.body, IfExpr)
    assert isinstance(result.body.then_branch, Application)

    """Integration with AST validation"""

def test_parsed_expression_passes_ast_validation():
    result = parse_expression(
        "let { double x = x * 2 } in double 10"
    )

    validate_expression(result)