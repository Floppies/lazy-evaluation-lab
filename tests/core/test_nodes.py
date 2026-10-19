import pytest

from dataclasses import FrozenInstanceError

from lazy_lab.source import SourceSpan
from lazy_lab.core.nodes import (
    CoreInt,
    CoreBool,
    CoreVar,
    CoreLam,
    CoreApp,
    CorePrimOp,
    CoreBinding,
    CoreLetRec,
    CoreCon,
    CoreConAlt,
    CoreCase,
    CoreProgram,
)


def test_curried_lambda():
    expression = CoreLam(
        "x",
        CoreLam(
            "y",
            CorePrimOp(
                "+",
                (CoreVar("x"), CoreVar("y")),
            ),
        ),
    )

    assert isinstance(expression.body, CoreLam)
    assert expression.body.parameter == "y"


def test_left_associative_application():
    expression = CoreApp(
        CoreApp(CoreVar("f"), CoreInt(2)),
        CoreInt(3),
    )

    assert isinstance(expression.function, CoreApp)
    assert expression.argument == CoreInt(3)


def test_recursive_bindings():
    expression = CoreLetRec(
        bindings=(
            CoreBinding("x", CoreVar("y")),
            CoreBinding("y", CoreInt(10)),
        ),
        body=CoreVar("x"),
    )

    assert len(expression.bindings) == 2
    assert expression.bindings[0].rhs == CoreVar("y")


def test_list_constructor():
    expression = CoreCon(
        "Cons",
        (
            CoreInt(1),
            CoreCon("Nil", ()),
        ),
    )

    assert expression.constructor == "Cons"
    assert expression.fields[1] == CoreCon("Nil", ())


def test_constructor_case():
    expression = CoreCase(
        scrutinee=CoreVar("xs"),
        alternatives=(
            CoreConAlt("Nil", (), CoreInt(0)),
            CoreConAlt(
                "Cons",
                ("x", "tail"),
                CoreInt(1),
            ),
        ),
    )

    assert len(expression.alternatives) == 2
    assert expression.alternatives[0].constructor == "Nil"


def test_core_program():
    program = CoreProgram(
        bindings=(
            CoreBinding("main", CoreBool(True)),
        )
    )

    assert len(program.bindings) == 1


def test_core_nodes_are_immutable():
    node = CoreVar("x")

    with pytest.raises(FrozenInstanceError):
        node.name = "y"


def test_core_equality_ignores_source_spans():
    first = CoreInt(
        42,
        span=SourceSpan(1, 1, 1, 3),
    )
    second = CoreInt(
        42,
        span=SourceSpan(5, 10, 5, 12),
    )

    assert first == second