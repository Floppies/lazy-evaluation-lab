from lazy_lab.frontend.parser import (
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
    ValueDefinition,
    Var,
    VarPattern,
)
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

