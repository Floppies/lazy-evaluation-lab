import pytest

from lazy_lab.ast.nodes import (
    Application,
    IntLiteral,
    ValueDefinition,
    Var,
)

from lazy_lab.ast.validation import (
    ASTValidationError,
    validate_expression,
    validate_program,
)

from lazy_lab.frontend.errors import (
    LexerError,
    ParserError,
)

from lazy_lab.frontend.parser import (
    parse_expression,
    parse_program,
)


@pytest.mark.parametrize(
    "source",
    [
        "42",
        "f x y",
        "1 + 2 * 3",
        "1 : 2 : []",
        "if True then 1 else 2",
        r"\x y -> x + y",
        "let { x = 10 } in x",
        "map double [1, 2, 3]",
    ],
)
def test_parsed_expressions_pass_structural_validation(source):
    expression = parse_expression(source)

    validate_expression(expression)

@pytest.mark.parametrize(
    "source",
    [
        "",
        "main = 42",
        "double x = x * 2\nmain = double 10",
        (
            "length [] = 0\n"
            "length (x:xs) = 1 + length xs\n"
            "main = length [1, 2, 3]"
        ),
        (
            "isEven n = if n == 0 then True else isOdd (n - 1)\n"
            "isOdd n = if n == 0 then False else isEven (n - 1)"
        ),
    ],
)
def test_parsed_programs_pass_structural_validation(source):
    program = parse_program(source)

    validate_program(program)

@pytest.mark.parametrize(
    "entry, source",
    [
        (parse_expression, "@"),
        (parse_program, "main = @"),
    ],
)
def test_lexer_errors_are_preserved(entry, source):
    with pytest.raises(LexerError):
        entry(source)

@pytest.mark.parametrize(
    "entry, source",
    [
        (parse_expression, "1 +"),
        (parse_expression, "[1,]"),
        (parse_program, "main ="),
        (parse_program, "f (x) = x"),
    ],
)
def test_parser_errors_are_preserved(entry, source):
    with pytest.raises(ParserError):
        entry(source)

def test_structural_error_is_not_a_parser_error():
    program = parse_program("f x x = x")

    with pytest.raises(
        ASTValidationError,
        match="Duplicate parameter binder",
    ):
        validate_program(program)

def test_parser_does_not_perform_semantic_checks():
    expression = parse_expression("1 unknown")

    expected = Application(
        IntLiteral(1),
        Var("unknown"),
    )

    assert expression == expected

    validate_expression(expression)

def test_expression_ast_is_consistent_with_program_rhs():
    expression_source = "let { x = 10 } in x + 2"

    standalone = parse_expression(expression_source)

    program = parse_program(
        f"main = {expression_source}"
    )

    definition = program.definitions[0]

    assert isinstance(definition, ValueDefinition)
    assert definition.rhs == standalone

def test_validation_does_not_modify_ast():
    program = parse_program(
        "double x = x * 2\n"
        "main = double 10"
    )

    original = program

    validate_program(program)

    assert program is original