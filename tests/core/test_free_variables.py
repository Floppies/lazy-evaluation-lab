
"""Free-variable analysis contracts for Core."""

import pytest

from lazy_lab.core.free_variables import free_variable_names
from lazy_lab.core.nodes import (
    CoreApp,
    CoreCase,
    CoreCon,
    CoreConAlt,
    CoreDefaultAlt,
    CoreIf,
    CoreInt,
    CoreLam,
    CoreLetRec,
    CoreBinding,
    CorePrimOp,
    CoreVar,
)


def test_lambda_parameter_is_not_free():
    expression = CoreLam("x", CoreVar("x"))

    assert free_variable_names(expression) == frozenset()


def test_lambda_captures_only_referenced_external_names():
    expression = CoreLam(
        "z",
        CorePrimOp(
            "+",
            (CoreVar("x"), CoreVar("z")),
        ),
    )

    assert free_variable_names(expression) == {"x"}


def test_nested_lambdas_respect_all_active_binders():
    expression = CoreLam(
        "x",
        CoreLam(
            "y",
            CoreApp(
                CoreVar("x"),
                CoreApp(CoreVar("g"), CoreVar("z")),
            ),
        ),
    )

    assert free_variable_names(expression) == {"g", "z"}


def test_nested_shadowing_does_not_expose_bound_names():
    expression = CoreLam(
        "x",
        CoreApp(
            CoreLam("x", CoreVar("x")),
            CoreVar("x"),
        ),
    )

    assert free_variable_names(expression) == frozenset()


def test_recursive_let_binds_all_group_names():
    expression = CoreLetRec(
        bindings=(
            CoreBinding("x", CoreVar("y")),
            CoreBinding("y", CoreVar("external")),
        ),
        body=CoreVar("x"),
    )

    assert free_variable_names(expression) == {"external"}


def test_let_scope_does_not_escape_its_expression():
    expression = CoreApp(
        CoreLetRec(
            bindings=(CoreBinding("x", CoreInt(1)),),
            body=CoreVar("x"),
        ),
        CoreVar("x"),
    )

    assert free_variable_names(expression) == {"x"}


def test_case_binders_are_local_to_each_alternative():
    expression = CoreCase(
        scrutinee=CoreVar("subject"),
        alternatives=(
            CoreConAlt(
                "Cons",
                ("head", "tail"),
                CoreVar("head"),
            ),
            CoreDefaultAlt(
                "fallback",
                CoreVar("head"),
            ),
        ),
    )

    assert free_variable_names(expression) == {
        "subject", "head"
    }


def test_constructor_and_conditional_fields_are_visited():
    expression = CoreIf(
        CoreVar("condition"),
        CoreCon("Cons", (CoreVar("head"), CoreVar("tail"))),
        CoreCon("Nil", ()),
    )

    assert free_variable_names(expression) == {
        "condition", "head", "tail"
    }


def test_global_and_predefined_names_remain_free():
    expression = CoreLam(
        "x",
        CoreApp(
            CoreApp(CoreVar("seq"), CoreVar("x")),
            CoreVar("global"),
        ),
    )

    assert free_variable_names(expression) == {
        "seq", "global"
    }


def test_deeply_nested_lambdas_do_not_recurse():
    expression = CoreVar("external")

    for index in range(3000):
        expression = CoreLam(
            f"parameter{index}",
            expression,
        )

    assert free_variable_names(expression) == {"external"}


def test_deep_application_tree_does_not_recurse():
    expression = CoreVar("f")

    for _ in range(3000):
        expression = CoreApp(
            expression,
            CoreVar("argument"),
        )

    assert free_variable_names(expression) == {
        "f", "argument"
    }


def test_invalid_input_is_rejected():
    with pytest.raises(TypeError):
        free_variable_names(42)
