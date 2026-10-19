import pytest

from lazy_lab.ast.validation import validate_expression, validate_program
from lazy_lab.ast import nodes as surface
from lazy_lab.frontend.parser import parse_expression

from lazy_lab.core import nodes as core
from lazy_lab.core.desugar import lower_expression
from lazy_lab.core.validation import validate_core_expression

from lazy_lab.frontend.parser import parse_program
from lazy_lab.core.desugar import (
    DesugaringError,
    lower_program,
)
from lazy_lab.core.validation import validate_core_program


@pytest.mark.parametrize(
    "source, expected",
    [
        ("42", core.CoreInt(42)),
        ("True", core.CoreBool(True)),
        ("False", core.CoreBool(False)),
        ("x", core.CoreVar("x")),
        (
            "-3",
            core.CorePrimOp(
                "negate",
                (core.CoreInt(3),),
            ),
        ),
        (
            "1 + 2 * 3",
            core.CorePrimOp(
                "+",
                (
                    core.CoreInt(1),
                    core.CorePrimOp(
                        "*",
                        (core.CoreInt(2), core.CoreInt(3)),
                    ),
                ),
            ),
        ),
        (
            "f x y",
            core.CoreApp(
                core.CoreApp(
                    core.CoreVar("f"),
                    core.CoreVar("x"),
                ),
                core.CoreVar("y"),
            ),
        ),
    ],
)
def test_basic_expression_lowering(source, expected):
    expression = parse_expression(source)
    validate_expression(expression)

    result = lower_expression(expression)
    validate_core_expression(result)

    assert result == expected

def test_multi_parameter_lambda_lowering():
    source = r"\x y -> x + y"

    expression = parse_expression(source)
    validate_expression(expression)

    result = lower_expression(expression)
    validate_core_expression(result)

    expected = core.CoreLam(
        "x",
        core.CoreLam(
            "y",
            core.CorePrimOp(
                "+",
                (
                    core.CoreVar("x"),
                    core.CoreVar("y"),
                ),
            ),
        ),
    )

    assert result == expected

def test_if_expression_lowering():
    source = "if x == 0 then 1 else x"

    expression = parse_expression(source)
    validate_expression(expression)

    result = lower_expression(expression)
    validate_core_expression(result)

    expected = core.CoreIf(
        condition=core.CorePrimOp(
            "==",
            (core.CoreVar("x"), core.CoreInt(0)),
        ),
        then_branch=core.CoreInt(1),
        else_branch=core.CoreVar("x"),
    )

    assert result == expected

def test_lowering_preserves_source_span():
    source = "1 + 2"

    surface_expression = parse_expression(source)
    result = lower_expression(surface_expression)

    assert result.span == surface_expression.span
    assert result.arguments[0].span == surface_expression.left.span
    assert result.arguments[1].span == surface_expression.right.span

@pytest.mark.parametrize(
    "source, expected",
    [
        (
            "[]",
            core.CoreCon("Nil", ()),
        ),
        (
            "[1]",
            core.CoreCon(
                "Cons",
                (core.CoreInt(1), core.CoreCon("Nil", ())),
            ),
        ),
        (
            "[1, 2]",
            core.CoreCon(
                "Cons",
                (
                    core.CoreInt(1),
                    core.CoreCon(
                        "Cons",
                        (
                            core.CoreInt(2),
                            core.CoreCon("Nil", ()),
                        ),
                    ),
                ),
            ),
        ),
    ],
)
def test_list_literal_lowering(source, expected):
    expression = parse_expression(source)
    validate_expression(expression)

    result = lower_expression(expression)
    validate_core_expression(result)

    assert result == expected

@pytest.mark.parametrize(
    "literal, cons",
    [
        ("[]", "[]"),
        ("[1]", "1 : []"),
        ("[1, 2]", "1 : 2 : []"),
        ("[1 + 2, 3]", "(1 + 2) : 3 : []"),
        ("[[1], [2]]", "[1] : [2] : []"),
    ],
)
def test_list_syntax_equivalence(literal, cons):
    literal_core = lower_expression(
        parse_expression(literal)
    )
    cons_core = lower_expression(
        parse_expression(cons)
    )

    validate_core_expression(literal_core)
    validate_core_expression(cons_core)

    assert literal_core == cons_core

def test_list_as_function_argument():
    expression = parse_expression("f [1, 2]")
    result = lower_expression(expression)

    assert isinstance(result, core.CoreApp)
    assert result.function == core.CoreVar("f")
    assert isinstance(result.argument, core.CoreCon)
    assert result.argument.constructor == "Cons"

def test_list_preserves_complex_elements():
    expression = parse_expression(
        "[1 + 2, if True then 3 else 4]"
    )

    result = lower_expression(expression)
    validate_core_expression(result)

    assert isinstance(result, core.CoreCon)

    first_element = result.fields[0]
    second_cons = result.fields[1]
    second_element = second_cons.fields[0]

    assert isinstance(first_element, core.CorePrimOp)
    assert first_element.operator == "+"

    assert isinstance(second_element, core.CoreIf)

def test_list_literal_source_spans():
    expression = parse_expression("[10, 20]")
    result = lower_expression(expression)

    assert result.span == expression.span

    first_element = result.fields[0]
    assert first_element.span == expression.elements[0].span

    second_cons = result.fields[1]
    assert second_cons.span == expression.span

    second_element = second_cons.fields[0]
    assert second_element.span == expression.elements[1].span

def test_cons_does_not_check_tail_type():
    expression = parse_expression("1 : 2")
    result = lower_expression(expression)

    validate_core_expression(result)

    assert result == core.CoreCon(
        "Cons",
        (
            core.CoreInt(1),
            core.CoreInt(2),
        ),
    )

def test_large_list_literal_lowering():
    source = "[" + ",".join(["1"] * 2000) + "]"

    expression = parse_expression(source)
    result = lower_expression(expression)

    validate_core_expression(result)

    assert isinstance(result, core.CoreCon)
    assert result.constructor == "Cons"

def test_local_value_lowering():
    expression = parse_expression(
        "let { x = 10 } in x"
    )

    result = lower_expression(expression)
    validate_core_expression(result)

    expected = core.CoreLetRec(
        bindings=(
            core.CoreBinding(
                "x",
                core.CoreInt(10),
            ),
        ),
        body=core.CoreVar("x"),
    )

    assert result == expected

def test_local_function_currying():
    expression = parse_expression(
        "let { add x y = x + y } in add 2 3"
    )

    result = lower_expression(expression)
    validate_core_expression(result)

    expected = core.CoreLetRec(
        bindings=(
            core.CoreBinding(
                "add",
                core.CoreLam(
                    "x",
                    core.CoreLam(
                        "y",
                        core.CorePrimOp(
                            "+",
                            (
                                core.CoreVar("x"),
                                core.CoreVar("y"),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        body=core.CoreApp(
            core.CoreApp(
                core.CoreVar("add"),
                core.CoreInt(2),
            ),
            core.CoreInt(3),
        ),
    )

    assert result == expected

def test_mutually_recursive_local_bindings():
    expression = parse_expression(
        "let { x = y; y = 10 } in x"
    )

    result = lower_expression(expression)
    validate_core_expression(result)

    assert result == core.CoreLetRec(
        bindings=(
            core.CoreBinding("x", core.CoreVar("y")),
            core.CoreBinding("y", core.CoreInt(10)),
        ),
        body=core.CoreVar("x"),
    )

def test_recursive_local_function():
    source = (
        "let { factorial n = "
        "if n == 0 then 1 else n * factorial (n - 1) } "
        "in factorial 5"
    )

    expression = parse_expression(source)
    result = lower_expression(expression)

    validate_core_expression(result)

    assert isinstance(result, core.CoreLetRec)

    binding = result.bindings[0]

    assert binding.name == "factorial"
    assert isinstance(binding.rhs, core.CoreLam)
    assert isinstance(binding.rhs.body, core.CoreIf)

def test_nested_let_shadowing():
    expression = parse_expression(
        "let { x = 10 } in let { x = 20 } in x"
    )

    result = lower_expression(expression)
    validate_core_expression(result)

    assert isinstance(result, core.CoreLetRec)
    assert isinstance(result.body, core.CoreLetRec)

    assert result.bindings[0].name == "x"
    assert result.body.bindings[0].name == "x"

def test_local_binding_rhs_is_not_evaluated():
    expression = parse_expression(
        "let { x = 1 + 2 } in 0"
    )

    result = lower_expression(expression)
    validate_core_expression(result)

    assert isinstance(
        result.bindings[0].rhs,
        core.CorePrimOp,
    )

    assert result.bindings[0].rhs.operator == "+"
    assert result.body == core.CoreInt(0)

def test_local_binding_preserves_source_spans():
    expression = parse_expression(
        "let { double x = x * 2 } in double 10"
    )

    result = lower_expression(expression)

    surface_binding = expression.bindings[0]
    core_binding = result.bindings[0]

    assert result.span == expression.span
    assert core_binding.span == surface_binding.span
    assert core_binding.rhs.span == surface_binding.span

    assert (
        core_binding.rhs.body.span
        == surface_binding.rhs.span
    )

    assert result.body.span == expression.body.span

def test_global_value_lowering():
    program = parse_program("main = 42")
    validate_program(program)

    result = lower_program(program)
    validate_core_program(result)

    assert result == core.CoreProgram(
        (
            core.CoreBinding(
                "main",
                core.CoreInt(42),
            ),
        ),
    )

def test_global_function_currying():
    program = parse_program("add x y = x + y")
    validate_program(program)

    result = lower_program(program)
    validate_core_program(result)

    expected = core.CoreProgram(
        (
            core.CoreBinding(
                "add",
                core.CoreLam(
                    "x",
                    core.CoreLam(
                        "y",
                        core.CorePrimOp(
                            "+",
                            (
                                core.CoreVar("x"),
                                core.CoreVar("y"),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )

    assert result == expected

def test_multiple_global_definitions():
    source = (
        "add x y = x + y\n"
        "double x = x * 2\n"
        "main = double (add 2 3)"
    )

    program = parse_program(source)
    validate_program(program)

    result = lower_program(program)
    validate_core_program(result)

    assert len(result.bindings) == 3

    assert [binding.name for binding in result.bindings] == [
        "add",
        "double",
        "main",
    ]

    assert isinstance(result.bindings[0].rhs, core.CoreLam)
    assert isinstance(result.bindings[1].rhs, core.CoreLam)
    assert isinstance(result.bindings[2].rhs, core.CoreApp)

def test_mutually_recursive_global_functions():
    source = (
        "isEven n = if n == 0 then True else isOdd (n - 1)\n"
        "isOdd n = if n == 0 then False else isEven (n - 1)"
    )

    program = parse_program(source)
    validate_program(program)

    result = lower_program(program)
    validate_core_program(result)

    assert len(result.bindings) == 2

    assert result.bindings[0].name == "isEven"
    assert result.bindings[1].name == "isOdd"

    assert isinstance(result.bindings[0].rhs, core.CoreLam)
    assert isinstance(result.bindings[1].rhs, core.CoreLam)

def test_empty_program_lowering():
    program = parse_program("")
    validate_program(program)

    result = lower_program(program)
    validate_core_program(result)

    assert result == core.CoreProgram(())

@pytest.mark.parametrize(
    "source",
    [
        "length [] = 0",
        "head (x:xs) = x",
        "map f (x:xs) = f x",
    ],
)
def test_constructor_patterns(source):
    program = parse_program(source)
    validate_program(program)
    lower_program(program)

def test_multiple_equations_are_not_silently_discarded():
    source = (
        "f x = 1\n"
        "f y = 2"
    )

    program = parse_program(source)
    validate_program(program)
    lower_program(program)

def test_global_source_spans_are_preserved():
    source = "double x = x * 2\nmain = double 10"

    program = parse_program(source)
    result = lower_program(program)

    assert result.span == program.span

    assert (
        result.bindings[0].span
        == program.definitions[0].span
    )

    assert (
        result.bindings[0].rhs.span
        == program.definitions[0].span
    )

    assert (
        result.bindings[1].span
        == program.definitions[1].span
    )

def test_deep_left_associative_expression_lowering():
    count = 2000
    source = " + ".join(["1"] * count)

    expression = parse_expression(source)
    result = lower_expression(expression)

    validate_core_expression(result)

    # Walk the left-associated Core tree iteratively.
    current = result
    operators = 0

    while isinstance(current, core.CorePrimOp):
        assert current.operator == "+"
        assert current.arguments[1] == core.CoreInt(1)

        current = current.arguments[0]
        operators += 1

    assert operators == count - 1
    assert current == core.CoreInt(1)

def test_deep_nested_let_lowering():
    expression: surface.Expr = surface.IntLiteral(0)

    for _ in range(1500):
        expression = surface.LetExpr(
            bindings=(
                surface.LocalBinding(
                    "x",
                    (),
                    surface.IntLiteral(1),
                ),
            ),
            body=expression,
        )

    result = lower_expression(expression)
    validate_core_expression(result)

    depth = 0
    current = result

    while isinstance(current, core.CoreLetRec):
        depth += 1
        current = current.body

    assert depth == 1500

@pytest.mark.parametrize(
    "source",
    [
        "1 + 2 * 3",
        r"\x y -> x + y",
        "if True then 1 else 2",
        "let { x = 10 } in x + 2",
        "[1, 2, 3]",
        "1 : 2 : []",
    ],
)
def test_standalone_and_program_rhs_lowering_are_equal(source):
    standalone = parse_expression(source)
    validate_expression(standalone)

    program = parse_program(f"main = {source}")
    validate_program(program)

    standalone_core = lower_expression(standalone)
    program_core = lower_program(program).bindings[0].rhs

    assert standalone_core == program_core

def test_foldr_program_lowering():
    source = (
        "foldr f z [] = z\n"
        "foldr f z (x:xs) = f x (foldr f z xs)\n"
        "main = foldr (\\x acc -> x + acc) 0 [1, 2, 3]"
    )

    program = parse_program(source)
    validate_program(program)

    result = lower_program(program)
    validate_core_program(result)

    assert [binding.name for binding in result.bindings] == [
        "foldr",
        "main",
    ]

    function = result.bindings[0].rhs

    assert isinstance(function, core.CoreLam)
    assert isinstance(function.body, core.CoreLam)
    assert isinstance(function.body.body, core.CoreLam)

    case = function.body.body.body

    assert isinstance(case, core.CoreCase)

    assert [
        alternative.constructor
        for alternative in case.alternatives
    ] == ["Nil", "Cons"]

def test_lowering_preserves_unused_recursive_binding():
    source = (
        "let { x = x } "
        "in if False then x else 10"
    )

    expression = parse_expression(source)
    validate_expression(expression)

    result = lower_expression(expression)
    validate_core_expression(result)

    assert isinstance(result, core.CoreLetRec)

    assert result.bindings == (
        core.CoreBinding("x", core.CoreVar("x")),
    )

    assert isinstance(result.body, core.CoreIf)

    assert result.body.condition == core.CoreBool(False)
    assert result.body.then_branch == core.CoreVar("x")
    assert result.body.else_branch == core.CoreInt(10)

def test_complete_program_lowering_is_deterministic():
    source = (
        "map f [] = []\n"
        "map f (x:xs) = f x : map f xs\n"
        "main = map (\\x -> x * 2) [1, 2, 3]"
    )

    program = parse_program(source)
    validate_program(program)

    first = lower_program(program)
    second = lower_program(program)

    validate_core_program(first)
    validate_core_program(second)

    assert first == second

    