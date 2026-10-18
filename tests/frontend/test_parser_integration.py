import pytest

from lazy_lab.frontend.errors import LexerError, ParserError
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
    LocalBinding,
    NilPattern,
    Program,
    SourceSpan,
    UnaryOp,
    ValueDefinition,
    Var,
    VarPattern,
)
from lazy_lab.frontend.tokens import TokenKind
from lazy_lab.ast.validation import (
    ASTValidationError,
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

    assert program == Program(
        (
            FunctionEquation("map", (VarPattern("f"), NilPattern()), ListLiteral(())),
            FunctionEquation(
                "map",
                (VarPattern("f"), ConsPattern(VarPattern("x"), VarPattern("xs"))),
                BinaryOp(
                    ":", Application(Var("f"), Var("x")),
                    Application(Application(Var("map"), Var("f")), Var("xs")),
                ),
            ),
            FunctionEquation(
                "double", (VarPattern("x"),), BinaryOp("*", Var("x"), IntLiteral(2))
            ),
            ValueDefinition(
                "main",
                Application(
                    Application(Var("map"), Var("double")),
                    ListLiteral((IntLiteral(1), IntLiteral(2), IntLiteral(3))),
                ),
            ),
        )
    )

def test_complex_expression_integration():
    source = (
        r"let { x = 10; double = \y -> y * 2 } "
        "in double x"
    )

    expression = parse_expression(source)
    validate_expression(expression)

    assert expression == LetExpr(
        (
            LocalBinding("x", (), IntLiteral(10)),
            LocalBinding(
                "double", (), LambdaExpr(("y",), BinaryOp("*", Var("y"), IntLiteral(2)))
            ),
        ),
        Application(Var("double"), Var("x")),
    )

def test_nested_shadowing_integration():
    source = (
        "let { x = 10 } "
        "in let { x = 20 } in x"
    )

    expression = parse_expression(source)
    validate_expression(expression)

    assert expression == LetExpr(
        (LocalBinding("x", (), IntLiteral(10)),),
        LetExpr((LocalBinding("x", (), IntLiteral(20)),), Var("x")),
    )

def test_variable_pattern_before_constructor_pattern():
    source = "f x = 10\nf [] = 20"

    program = parse_program(source)
    validate_program(program)

    assert program == Program(
        (
            FunctionEquation("f", (VarPattern("x"),), IntLiteral(10)),
            FunctionEquation("f", (NilPattern(),), IntLiteral(20)),
        )
    )

def test_line_endings_produce_equivalent_ast():
    source_lf = (
        "double x = x * 2\n"
        "main = double 10"
    )

    source_crlf = source_lf.replace("\n", "\r\n")

    expected = Program(
        (
            FunctionEquation(
                "double", (VarPattern("x"),), BinaryOp("*", Var("x"), IntLiteral(2))
            ),
            ValueDefinition("main", Application(Var("double"), IntLiteral(10))),
        )
    )
    assert parse_program(source_lf) == expected
    assert parse_program(source_crlf) == expected


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


@pytest.mark.parametrize(
    "endings",
    [
        pytest.param(("\n",) * 5, id="lf"),
        pytest.param(("\r\n",) * 5, id="crlf"),
        pytest.param(("\r\n", "\n", "\r\n", "\n", "\r\n"), id="mixed"),
    ],
)
def test_spans_survive_comments_tabs_blank_lines_and_line_endings(endings):
    lines = [
        "-- leading comment",
        "",
        "\tdouble x = x * 2 -- twice",
        "main = double (10)",
        "",
        "-- trailing comment",
    ]
    source = "".join(line + ending for line, ending in zip(lines[:-1], endings)) + lines[-1]

    program = parse_program(source)
    validate_program(program)

    assert program == Program(
        (
            FunctionEquation(
                "double", (VarPattern("x"),), BinaryOp("*", Var("x"), IntLiteral(2))
            ),
            ValueDefinition("main", Application(Var("double"), IntLiteral(10))),
        )
    )
    # AST equality ignores spans, so locations need independent assertions.
    assert program.span == SourceSpan(3, 2, 4, 19)
    function, main = program.definitions
    assert function.span == SourceSpan(3, 2, 3, 18)
    assert function.parameters[0].span == SourceSpan(3, 9, 3, 10)
    assert function.rhs.span == SourceSpan(3, 13, 3, 18)
    assert function.rhs.left.span == SourceSpan(3, 13, 3, 14)
    assert function.rhs.right.span == SourceSpan(3, 17, 3, 18)
    assert main.span == SourceSpan(4, 1, 4, 19)
    assert main.rhs.span == SourceSpan(4, 8, 4, 19)
    assert main.rhs.function.span == SourceSpan(4, 8, 4, 14)
    assert main.rhs.argument.span == SourceSpan(4, 16, 4, 18)


@pytest.mark.parametrize("parse", [parse_expression, parse_program], ids=["expression", "program"])
@pytest.mark.parametrize(
    "source", [None, 1, True, b"x", []], ids=["none", "integer", "boolean", "bytes", "list"]
)
def test_parser_entry_points_propagate_invalid_source_type(parse, source):
    with pytest.raises(TypeError, match="Source must be a string"):
        parse(source)


@pytest.mark.parametrize(
    "parse,source,message,line,column",
    [
        pytest.param(
            parse_expression, "1 + @", "Unexpected character", 1, 5, id="expression-character"
        ),
        pytest.param(
            parse_program, "main = @", "Unexpected character", 1, 8, id="program-character"
        ),
        pytest.param(
            parse_expression, "123abc", "Invalid suffix", 1, 4, id="integer-suffix"
        ),
        pytest.param(
            parse_program, "main = Test", "Invalid identifier", 1, 8, id="invalid-identifier"
        ),
        pytest.param(
            parse_program, "ok = 0\r\n\tmain = @", "Unexpected character", 2, 9,
            id="after-crlf-and-tab",
        ),
        pytest.param(
            parse_program, "f (_:xs) = x", "Unexpected character", 1, 4,
            id="unsupported-wildcard",
        ),
    ],
)
def test_lexical_errors_propagate_through_parser_entry_points(
    parse, source, message, line, column
):
    with pytest.raises(LexerError, match=message) as error:
        parse(source)

    assert (error.value.line, error.value.column) == (line, column)
    assert str(error.value).startswith(f"{line}:{column}: ")


@pytest.mark.parametrize(
    "parse,source,message,line,column,kind",
    [
        pytest.param(
            parse_expression, "(1 +", "Expected an expression, found EOF",
            1, 5, TokenKind.EOF, id="incomplete-expression",
        ),
        pytest.param(
            parse_program, "main = [1,]", "Expected an expression, found RBRACKET",
            1, 11, TokenKind.RBRACKET, id="invalid-list-element",
        ),
        pytest.param(
            parse_program, "ok = 0\r\n\tmain = [1,]", "Expected an expression, found RBRACKET",
            2, 12, TokenKind.RBRACKET, id="after-crlf-and-tab",
        ),
    ],
)
def test_syntax_errors_report_the_offending_token(parse, source, message, line, column, kind):
    with pytest.raises(ParserError, match=message) as error:
        parse(source)

    assert (error.value.line, error.value.column) == (line, column)
    assert error.value.token.kind == kind
    assert str(error.value).startswith(f"{line}:{column}: ")


@pytest.mark.parametrize(
    "parse,validate,source,message,line,column",
    [
        pytest.param(
            parse_expression, validate_expression, r"\x x -> x",
            "Duplicate parameter", 1, 1, id="lambda-parameters",
        ),
        pytest.param(
            parse_expression, validate_expression, "let {f x x=x} in f",
            "Duplicate parameter", 1, 6, id="local-function-parameters",
        ),
        pytest.param(
            parse_expression, validate_expression, "let {x=1;x=2} in x",
            "Duplicate local binding", 1, 10, id="local-binding-names",
        ),
        pytest.param(
            parse_program, validate_program, "f [] x=x",
            "final parameter", 1, 3, id="nil-pattern-position",
        ),
        pytest.param(
            parse_program, validate_program, "f (x:xs) y=x",
            "final parameter", 1, 3, id="cons-pattern-position",
        ),
        pytest.param(
            parse_program, validate_program, "f x (x:xs)=x",
            "Duplicate parameter binder", 1, 6, id="cons-binder-overlaps-parameter",
        ),
        pytest.param(
            parse_program, validate_program, "f (x:x)=x",
            "Duplicate binder in ConsPattern", 1, 6, id="duplicate-cons-binder",
        ),
        pytest.param(
            parse_program, validate_program, "f x=x\nf x y=x",
            "Inconsistent arity", 2, 1, id="equation-arities",
        ),
        pytest.param(
            parse_program, validate_program, "f x=x\ng=1\nf y=y",
            "Non-consecutive definitions", 3, 1, id="separated-equation-groups",
        ),
        pytest.param(
            parse_program, validate_program, "f=1\nf x=x",
            "Duplicate top-level definition", 2, 1, id="value-before-function",
        ),
        pytest.param(
            parse_program, validate_program, "f x=x\nf=1",
            "Duplicate top-level definition", 2, 1, id="function-before-value",
        ),
        pytest.param(
            parse_program, validate_program, "main=1\nmain=2",
            "Duplicate top-level definition", 2, 1, id="duplicate-main",
        ),
        pytest.param(
            parse_program, validate_program, "main x=x",
            "main must be a top-level value definition", 1, 1, id="main-function",
        ),
    ],
)
def test_structural_errors_are_rejected_after_successful_parsing(
    parse, validate, source, message, line, column
):
    # This call must succeed independently of structural validation.
    tree = parse(source)

    with pytest.raises(ASTValidationError, match=message) as error:
        validate(tree)

    assert str(error.value).startswith(f"{line}:{column}: ")


@pytest.mark.parametrize(
    "parse,validate,source,expected",
    [
        pytest.param(
            parse_program, validate_program, "f []=0",
            Program((FunctionEquation("f", (NilPattern(),), IntLiteral(0)),)),
            id="non-exhaustive-equation-without-main",
        ),
        pytest.param(
            parse_program, validate_program, "f []=0\nf []=1",
            Program(
                (
                    FunctionEquation("f", (NilPattern(),), IntLiteral(0)),
                    FunctionEquation("f", (NilPattern(),), IntLiteral(1)),
                )
            ),
            id="redundant-equation",
        ),
        pytest.param(
            parse_program, validate_program, "f x=g x\ng x=f x",
            Program(
                (
                    FunctionEquation("f", (VarPattern("x"),), Application(Var("g"), Var("x"))),
                    FunctionEquation("g", (VarPattern("x"),), Application(Var("f"), Var("x"))),
                )
            ),
            id="top-level-mutual-recursion",
        ),
        pytest.param(
            parse_program, validate_program, "loop=loop",
            Program((ValueDefinition("loop", Var("loop")),)),
            id="top-level-self-recursion",
        ),
        pytest.param(
            parse_expression, validate_expression, "let {f x=g x;g x=f x} in f 10",
            LetExpr(
                (
                    LocalBinding("f", ("x",), Application(Var("g"), Var("x"))),
                    LocalBinding("g", ("x",), Application(Var("f"), Var("x"))),
                ),
                Application(Var("f"), IntLiteral(10)),
            ),
            id="local-mutual-recursion",
        ),
        pytest.param(
            parse_expression, validate_expression, "let {x=x} in x",
            LetExpr((LocalBinding("x", (), Var("x")),), Var("x")),
            id="local-self-recursion",
        ),
        pytest.param(
            parse_expression, validate_expression, "unknown", Var("unknown"),
            id="unresolved-expression-name",
        ),
        pytest.param(
            parse_program, validate_program, "main=unknown",
            Program((ValueDefinition("main", Var("unknown")),)),
            id="unresolved-program-name",
        ),
        pytest.param(
            parse_expression, validate_expression, "if 0 then 1 else 2",
            IfExpr(IntLiteral(0), IntLiteral(1), IntLiteral(2)),
            id="condition-type-deferred-to-runtime",
        ),
        pytest.param(
            parse_expression, validate_expression, "True + 1",
            BinaryOp("+", BoolLiteral(True), IntLiteral(1)),
            id="primitive-types-deferred-to-runtime",
        ),
        pytest.param(
            parse_expression, validate_expression, "1 : 2",
            BinaryOp(":", IntLiteral(1), IntLiteral(2)),
            id="cons-tail-type-deferred-to-runtime",
        ),
    ],
)
def test_structural_validation_preserves_deferred_semantic_cases(
    parse, validate, source, expected
):
    tree = parse(source)

    assert tree == expected
    validate(tree)


def test_selected_expression_can_be_parsed_separately_from_program():
    program = parse_program("double x = x * 2")
    expression = parse_expression("double 3")

    validate_program(program)
    validate_expression(expression)

    assert program == Program(
        (FunctionEquation("double", (VarPattern("x"),), BinaryOp("*", Var("x"), IntLiteral(2))),)
    )
    assert expression == Application(Var("double"), IntLiteral(3))


@pytest.mark.parametrize("ending", ["", "\n", "\r\n"], ids=["eof", "lf", "crlf"])
def test_trailing_inline_comments_preserve_the_definition(ending):
    program = parse_program("main = 42 -- result" + ending)

    validate_program(program)

    assert program == Program((ValueDefinition("main", IntLiteral(42)),))
    assert program.span == SourceSpan(1, 1, 1, 10)
    assert program.definitions[0].rhs.span == SourceSpan(1, 8, 1, 10)


@pytest.mark.parametrize("source", [" \t ", "\t\r\n \t", " \t-- comment"])
def test_whitespace_only_programs_pass_structural_validation(source):
    program = parse_program(source)

    validate_program(program)

    assert program == Program(())

