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
    ListLiteral,
    Program,
    ValueDefinition,
    FunctionEquation,
    VarPattern,
    NilPattern,
    ConsPattern,
)
from lazy_lab.frontend.tokens import TokenKind
from lazy_lab.frontend.parser import parse_expression
from lazy_lab.frontend.parser import parse_program
from lazy_lab.frontend.errors import ParserError
from lazy_lab.ast.validation import (
    validate_expression,
    validate_program,
    ASTValidationError,
)


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

"""Simple definitions"""

def test_value_definition():
    program = parse_program("answer = 42")

    assert program == Program((
        ValueDefinition(
            name="answer",
            rhs=IntLiteral(42),
        ),
    ))


def test_function_definition():
    program = parse_program("double x = x * 2")

    assert program == Program((
        FunctionEquation(
            name="double",
            parameters=(VarPattern("x"),),
            rhs=BinaryOp("*", Var("x"), IntLiteral(2)),
        ),
    ))

def test_multiple_function_equations():
    source = (
        "length [] = 0\n"
        "length (x:xs) = 1 + length xs\n"
    )

    program = parse_program(source)

    assert len(program.definitions) == 2

    first, second = program.definitions

    assert isinstance(first, FunctionEquation)
    assert isinstance(second, FunctionEquation)

    assert first.name == second.name == "length"

    assert first.parameters == (NilPattern(),)

    assert second.parameters == (
        ConsPattern(
            VarPattern("x"),
            VarPattern("xs"),
        ),
    )

def test_complete_program():
    source = (
        "double x = x * 2\n"
        "main = double [1, 2, 3]\n"
    )

    program = parse_program(source)

    assert len(program.definitions) == 2

    assert isinstance(
        program.definitions[0],
        FunctionEquation,
    )

    assert isinstance(
        program.definitions[1],
        ValueDefinition,
    )

def test_blank_lines_and_comments():
    source = (
        "\n"
        "length [] = 0\n"
        "\n"
        "-- Non-empty lists\n"
        "length (x:xs) = 1 + length xs\n"
        "\n"
        "main = length [1, 2, 3]\n"
    )

    program = parse_program(source)

    assert len(program.definitions) == 3

    assert [
        definition.name
        for definition in program.definitions
    ] == ["length", "length", "main"]

@pytest.mark.parametrize(
    "source",
    [
        "",
        "\n",
        "\n\n",
        "-- Only a comment",
        "-- Comment\n\n",
    ],
)
def test_empty_program(source):
    assert parse_program(source) == Program(())

@pytest.mark.parametrize(
    "source",
    [
        "42",
        "map double [1, 2, 3]",
        "main =",
        "main = 1 +",
        "f (x) = x",
        "f (x:y:xs) = x",
        "f [x] = x",
        "main = 1\n42",
    ],
)
def test_invalid_program_syntax(source):
    with pytest.raises(ParserError):
        parse_program(source)

def test_parsed_program_passes_validation():
    source = (
        "length [] = 0\n"
        "length (x:xs) = 1 + length xs\n"
        "main = length [1, 2, 3]\n"
    )

    program = parse_program(source)

    validate_program(program)

def test_parser_preserves_structurally_invalid_equations():
    source = "f x x = x"

    program = parse_program(source)

    assert isinstance(
        program.definitions[0],
        FunctionEquation,
    )

    with pytest.raises(
        ASTValidationError,
        match="Duplicate parameter",
    ):
        validate_program(program)

def test_definition_source_spans():
    source = (
        "x = 10\n"
        "main = x + 2"
    )

    program = parse_program(source)

    assert program.definitions[0].span == SourceSpan(
        1, 1, 1, 7
    )

    assert program.definitions[1].span == SourceSpan(
        2, 1, 2, 13
    )

    assert program.span == SourceSpan(
        1, 1, 2, 13
    )


def test_cons_pattern_source_spans():
    program = parse_program("f (x:xs) = x")

    equation = program.definitions[0]
    pattern = equation.parameters[0]

    assert pattern.span == SourceSpan(1, 3, 1, 9)
    assert pattern.head.span == SourceSpan(1, 4, 1, 5)
    assert pattern.tail.span == SourceSpan(1, 6, 1, 8)


@pytest.mark.parametrize(
    "source, line, column, kind",
    [
        ("(1 + )", 1, 6, TokenKind.RPAREN),
        ("if True then 1", 1, 15, TokenKind.EOF),
        ("let { x = 1 } x", 1, 15, TokenKind.IDENT),
        ("[1,]", 1, 4, TokenKind.RBRACKET),
        ("1 < 2 < 3", 1, 7, TokenKind.LT),
    ],
)
def test_parser_error_location(source, line, column, kind):
    with pytest.raises(ParserError) as error:
        parse_expression(source)

    assert error.value.line == line
    assert error.value.column == column
    assert error.value.token.kind == kind
    assert str(error.value).startswith(f"{line}:{column}:")

@pytest.mark.parametrize(
    "source",
    [
        "main = 1 +\n2",
        "main = [1,\n2]",
        "main = let { x = 1;\n y = 2 } in y",
        "main = 1\n+ 2",
        "main = 1\n42",
    ],
)
def test_multiline_definitions_are_rejected(source):
    with pytest.raises(ParserError):
        parse_program(source)

def test_error_on_second_line():
    source = "x = 10\nmain = 1 +"

    with pytest.raises(ParserError) as error:
        parse_program(source)

    assert error.value.line == 2
    assert error.value.column == 11
    assert error.value.token.kind == TokenKind.EOF

@pytest.mark.parametrize(
    "source",
    [
        "42)",
        "x ]",
        "1 + 2, garbage",
        "True False )",
    ],
)
def test_expression_cannot_leave_unconsumed_tokens(source):
    with pytest.raises(ParserError):
        parse_expression(source)

def test_application_on_right_side_of_addition():
    assert parse_expression("1 + 2 garbage") == BinaryOp(
        "+",
        IntLiteral(1),
        Application(
            IntLiteral(2),
            Var("garbage"),
        ),
    )

def test_application_does_not_require_function_type():
    result = parse_expression("42 43")

    assert result == Application(
        IntLiteral(42),
        IntLiteral(43),
    )

def test_nested_expression_spans():
    source = "f (1 + 2)"
    result = parse_expression(source)

    assert isinstance(result, Application)
    assert result.span == SourceSpan(1, 1, 1, 10)

    assert result.function.span == SourceSpan(1, 1, 1, 2)

    argument = result.argument
    assert isinstance(argument, BinaryOp)
    assert argument.span == SourceSpan(1, 4, 1, 9)

    assert argument.left.span == SourceSpan(1, 4, 1, 5)
    assert argument.right.span == SourceSpan(1, 8, 1, 9)

def test_let_and_binding_spans():
    source = "let { x = 1 } in x"
    result = parse_expression(source)

    assert isinstance(result, LetExpr)
    assert result.span == SourceSpan(
        1, 1, 1, len(source) + 1
    )

    binding = result.bindings[0]

    assert binding.span == SourceSpan(1, 7, 1, 12)
    assert binding.rhs.span == SourceSpan(1, 11, 1, 12)

def test_duplicate_parameter_is_ast_validation_error():
    program = parse_program("f x x = x")

    assert isinstance(
        program.definitions[0],
        FunctionEquation,
    )

    with pytest.raises(ASTValidationError) as error:
        validate_program(program)

    assert "Duplicate parameter binder" in str(error.value)

def test_main_must_be_value_definition():
    program = parse_program("main x = x")

    with pytest.raises(ASTValidationError):
        validate_program(program)

def test_comments_do_not_break_equation_groups():
    source = (
        "length [] = 0\n"
        "\n"
        "-- Non-empty list\n"
        "length (x:xs) = 1 + length xs\n"
    )

    program = parse_program(source)

    assert len(program.definitions) == 2

    # Consecutive in the AST, even though
    # they were separated in the source.
    validate_program(program)