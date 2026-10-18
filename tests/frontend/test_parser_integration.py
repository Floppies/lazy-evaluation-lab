import pytest

from lazy_lab.frontend.errors import ParserError
from lazy_lab.frontend.parser import (
    MAX_PARSER_NESTING,
    parse_expression,
    parse_program,
)
from lazy_lab.ast.nodes import (
    Application,
    BinaryOp,
    BoolLiteral,
    ConsPattern,
    FunctionEquation,
    IfExpr,
    IntLiteral,
    LambdaExpr,
    LetExpr,
    ListLiteral,
    NilPattern,
    UnaryOp,
    ValueDefinition,
    Var,
    VarPattern,
)
from lazy_lab.frontend.tokens import TokenKind
from lazy_lab.ast.validation import (
    validate_expression,
    validate_program,
)


def test_map_program_integration():
    source = (
        "map f [] = []\n"
        "map f (x:xs) = f x : map f xs\n"
        "\n"
        "double x = x * 2\n"
        "main = map double [1, 2, 3]\n"
    )

    program = parse_program(source)
    validate_program(program)

    assert len(program.definitions) == 4

    first, second, third, fourth = program.definitions

    assert isinstance(first, FunctionEquation)
    assert isinstance(first.parameters[-1], NilPattern)

    assert isinstance(second, FunctionEquation)
    assert isinstance(second.parameters[-1], ConsPattern)
    assert isinstance(second.rhs, BinaryOp)
    assert second.rhs.operator == ":"

    assert isinstance(third, FunctionEquation)
    assert third.name == "double"

    assert isinstance(fourth, ValueDefinition)
    assert fourth.name == "main"
    assert isinstance(fourth.rhs, Application)

def test_complex_expression_integration():
    source = (
        r"let { x = 10; double = \y -> y * 2 } "
        "in double x"
    )

    expression = parse_expression(source)
    validate_expression(expression)

    assert isinstance(expression, LetExpr)
    assert len(expression.bindings) == 2

    assert isinstance(expression.bindings[1].rhs, LambdaExpr)
    assert isinstance(expression.body, Application)

def test_nested_shadowing_integration():
    source = (
        "let { x = 10 } "
        "in let { x = 20 } in x"
    )

    expression = parse_expression(source)
    validate_expression(expression)

    assert isinstance(expression, LetExpr)
    assert isinstance(expression.body, LetExpr)

def test_variable_pattern_before_constructor_pattern():
    source = "f x = 10\nf [] = 20"

    program = parse_program(source)
    validate_program(program)

    assert len(program.definitions) == 2
    assert isinstance(
        program.definitions[0].parameters[0],
        VarPattern,
    )
    assert isinstance(
        program.definitions[1].parameters[0],
        NilPattern,
    )

def test_line_endings_produce_equivalent_ast():
    source_lf = (
        "double x = x * 2\n"
        "main = double 10"
    )

    source_crlf = source_lf.replace("\n", "\r\n")

    assert parse_program(source_lf) == parse_program(source_crlf)


def test_nesting_budget_is_reused_between_program_definitions():
    expression = "(" * MAX_PARSER_NESTING + "0" + ")" * MAX_PARSER_NESTING
    source = "first = " + expression + "\nsecond = " + expression

    program = parse_program(source)
    validate_program(program)

    assert [definition.name for definition in program.definitions] == ["first", "second"]
    assert all(definition.rhs == IntLiteral(0) for definition in program.definitions)


@pytest.mark.parametrize(
    "source,node_type",
    [
        pytest.param("- " * MAX_PARSER_NESTING + "0", UnaryOp, id="unary-negation"),
        pytest.param(
            "1 : " * (MAX_PARSER_NESTING - 1) + "[]", BinaryOp, id="cons-and-empty-list"
        ),
        pytest.param(
            "[" * MAX_PARSER_NESTING + "0" + "]" * MAX_PARSER_NESTING,
            ListLiteral,
            id="nested-lists",
        ),
    ],
)
def test_parsed_expression_at_nesting_limit_passes_validation(source, node_type):
    expression = parse_expression(source)

    validate_expression(expression)
    assert isinstance(expression, node_type)


@pytest.mark.parametrize("ending", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_program_nesting_error_preserves_location_after_newline_and_tab(ending):
    prefix = "main = \t"
    expression = "(" * (MAX_PARSER_NESTING + 1) + "0" + ")" * (MAX_PARSER_NESTING + 1)
    source = "first = 0" + ending + prefix + expression

    with pytest.raises(ParserError, match="Maximum parser nesting depth") as error:
        parse_program(source)

    column = len(prefix) + MAX_PARSER_NESTING + 1
    assert (error.value.line, error.value.column) == (2, column)
    assert error.value.token.kind == TokenKind.LPAREN
    assert str(error.value).startswith(f"2:{column}: ")

