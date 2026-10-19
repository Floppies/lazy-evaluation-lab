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