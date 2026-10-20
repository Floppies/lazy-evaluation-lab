import pytest

from lazy_lab.frontend.parser import parse_program
from lazy_lab.ast.validation import validate_program
from lazy_lab.core import nodes as core
from lazy_lab.core.desugar import lower_program
from lazy_lab.core.validation import validate_core_program
from lazy_lab.semantics.name_resolution import (
    NameResolutionError,
    check_surface_names,
    check_core_names,
)


def check_source_pipeline(source: str) -> None:
    surface_program = parse_program(source)
    validate_program(surface_program)
    check_surface_names(surface_program)

    core_program = lower_program(surface_program)
    validate_core_program(core_program)
    check_core_names(core_program)


def check_core_expression(expr: core.CoreExpr) -> None:
    program = core.CoreProgram(
        (
            core.CoreBinding("main", expr),
        )
    )

    validate_core_program(program)
    check_core_names(program)

@pytest.mark.parametrize(
    "source",
    [
        "main = 42",
        "main = double 10\ndouble x = x * 2",
        "main = (\\x -> x + 1) 10",
        "main = let { x = y; y = 10 } in x",
        "main = let { x = x } in 10",
        (
            "f x [] = x\n"
            "f y (h:t) = y\n"
            "main = f 10 []"
        ),
        (
            "map f [] = []\n"
            "map f (x:xs) = f x : map f xs\n"
            "main = map (\\x -> x + 1) [1, 2, 3]"
        ),
    ],
)
def test_valid_core_name_resolution(source):
    check_source_pipeline(source)

def test_undefined_core_reference():
    program = core.CoreProgram(
        (
            core.CoreBinding(
                "main",
                core.CoreVar("missing"),
            ),
        )
    )

    validate_core_program(program)

    with pytest.raises(
        NameResolutionError,
        match="missing",
    ):
        check_core_names(program)

def test_constructor_binders_do_not_leak():
    expression = core.CoreCase(
        scrutinee=core.CoreCon("Nil", ()),
        alternatives=(
            core.CoreConAlt(
                "Nil",
                (),
                core.CoreVar("head"),
            ),
            core.CoreConAlt(
                "Cons",
                ("head", "tail"),
                core.CoreInt(1),
            ),
        ),
    )

    with pytest.raises(
        NameResolutionError,
        match="head",
    ):
        check_core_expression(expression)

def test_case_scrutinee_cannot_see_alternative_binders():
    expression = core.CoreCase(
        scrutinee=core.CoreVar("head"),
        alternatives=(
            core.CoreConAlt(
                "Cons",
                ("head", "tail"),
                core.CoreInt(1),
            ),
        ),
    )

    with pytest.raises(
        NameResolutionError,
        match="head",
    ):
        check_core_expression(expression)

def test_default_alternative_binder_is_visible():
    expression = core.CoreCase(
        scrutinee=core.CoreInt(10),
        alternatives=(
            core.CoreDefaultAlt(
                "value",
                core.CoreVar("value"),
            ),
        ),
    )

    check_core_expression(expression)

def test_deeply_nested_core_scopes():
    expression: core.CoreExpr = core.CoreVar("x")

    for _ in range(2000):
        expression = core.CoreLam(
            "x",
            expression,
        )

    check_core_expression(expression)

def test_undefined_reference_in_deep_core_tree():
    expression: core.CoreExpr = core.CoreVar("missing")

    for _ in range(2000):
        expression = core.CoreLam(
            "x",
            expression,
        )

    with pytest.raises(
        NameResolutionError,
        match="missing",
    ):
        check_core_expression(expression)

def test_core_letrec_binding_does_not_escape():
    expression = core.CoreApp(
        function=core.CoreLetRec(
            bindings=(
                core.CoreBinding(
                    "local",
                    core.CoreInt(10),
                ),
            ),
            body=core.CoreVar("local"),
        ),
        argument=core.CoreVar("local"),
    )

    with pytest.raises(
        NameResolutionError,
        match="local",
    ):
        check_core_expression(expression)

def test_default_binder_does_not_escape_its_alternative():
    expression = core.CoreCase(
        scrutinee=core.CoreCon("Nil", ()),
        alternatives=(
            core.CoreConAlt(
                "Nil",
                (),
                core.CoreVar("captured"),
            ),
            core.CoreDefaultAlt(
                "captured",
                core.CoreInt(1),
            ),
        ),
    )

    with pytest.raises(
        NameResolutionError,
        match="captured",
    ):
        check_core_expression(expression)