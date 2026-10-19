import pytest

from lazy_lab.ast.validation import validate_expression
from lazy_lab.frontend.parser import parse_expression

from lazy_lab.core import nodes as core
from lazy_lab.core.desugar import lower_expression
from lazy_lab.core.validation import validate_core_expression


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