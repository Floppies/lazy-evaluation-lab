import pytest

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
    CoreDefaultAlt,
    CoreCase,
    CoreProgram,
)

from lazy_lab.core.validation import (
    CoreValidationError,
    validate_core_expression,
    validate_core_program,
)


def test_curried_function_is_valid():
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

    validate_core_expression(expression)


def test_recursive_bindings_are_valid():
    expression = CoreLetRec(
        bindings=(
            CoreBinding("x", CoreVar("y")),
            CoreBinding("y", CoreInt(10)),
        ),
        body=CoreVar("x"),
    )

    validate_core_expression(expression)


def test_internal_identifiers_are_valid():
    expression = CoreLam(
        "$arg0",
        CoreVar("$arg0"),
    )

    validate_core_expression(expression)


def test_missing_name_is_not_a_structural_error():
    validate_core_expression(CoreVar("unknown"))


def test_potential_runtime_type_error_is_structurally_valid():
    expression = CoreApp(CoreInt(1), CoreBool(True))

    validate_core_expression(expression)


def test_non_exhaustive_case_is_valid():
    expression = CoreCase(
        CoreVar("xs"),
        (
            CoreConAlt("Nil", (), CoreInt(0)),
        ),
    )

    validate_core_expression(expression)


def test_nested_shadowing_is_valid():
    expression = CoreLetRec(
        (CoreBinding("x", CoreInt(1)),),
        CoreLetRec(
            (CoreBinding("x", CoreInt(2)),),
            CoreVar("x"),
        ),
    )

    validate_core_expression(expression)


def test_empty_core_program_is_valid():
    validate_core_program(CoreProgram(()))

@pytest.mark.parametrize(
    "expression, message",
    [
        (CoreInt(True), "CoreInt requires an integer"),
        (CoreBool(1), "CoreBool requires a boolean"),
        (
            CorePrimOp("+", (CoreInt(1),)),
            "expects 2 arguments",
        ),
        (
            CorePrimOp("negate", (CoreInt(1), CoreInt(2))),
            "expects 1 arguments",
        ),
        (
            CorePrimOp("/", (CoreInt(4), CoreInt(2))),
            "Unsupported primitive",
        ),
        (
            CoreCon("Cons", (CoreInt(1),)),
            "expects 2 fields",
        ),
        (
            CoreCon("Pair", ()),
            "Unsupported Core constructor",
        ),
        (
            CoreLetRec((), CoreInt(0)),
            "requires at least one binding",
        ),
        (
            CoreCase(CoreVar("xs"), ()),
            "requires at least one alternative",
        ),
        (
            CoreVar("Invalid"),
            "Invalid Core identifier",
        ),
        (
            CoreApp(CoreInt(1), "not an expression"),
            "must be a CoreExpr",
        ),
    ],
)
def test_invalid_core_expressions(expression, message):
    with pytest.raises(CoreValidationError, match=message):
        validate_core_expression(expression)

def test_duplicate_recursive_bindings_are_rejected():
    expression = CoreLetRec(
        (
            CoreBinding("x", CoreInt(1)),
            CoreBinding("x", CoreInt(2)),
        ),
        CoreVar("x"),
    )

    with pytest.raises(
        CoreValidationError,
        match="Duplicate Core binding",
    ):
        validate_core_expression(expression)


def test_duplicate_global_bindings_are_rejected():
    program = CoreProgram(
        (
            CoreBinding("main", CoreInt(1)),
            CoreBinding("main", CoreInt(2)),
        )
    )

    with pytest.raises(
        CoreValidationError,
        match="Duplicate Core binding",
    ):
        validate_core_program(program)


def test_duplicate_case_constructors_are_rejected():
    expression = CoreCase(
        CoreVar("xs"),
        (
            CoreConAlt("Nil", (), CoreInt(1)),
            CoreConAlt("Nil", (), CoreInt(2)),
        ),
    )

    with pytest.raises(
        CoreValidationError,
        match="Duplicate case constructor",
    ):
        validate_core_expression(expression)


def test_multiple_default_alternatives_are_rejected():
    expression = CoreCase(
        CoreVar("xs"),
        (
            CoreDefaultAlt("x", CoreInt(1)),
            CoreDefaultAlt("y", CoreInt(2)),
        ),
    )

    with pytest.raises(
        CoreValidationError,
        match="Multiple default alternatives",
    ):
        validate_core_expression(expression)


def test_duplicate_pattern_binders_are_rejected():
    expression = CoreCase(
        CoreVar("xs"),
        (
            CoreConAlt(
                "Cons",
                ("x", "x"),
                CoreVar("x"),
            ),
        ),
    )

    with pytest.raises(
        CoreValidationError,
        match="Duplicate pattern binder",
    ):
        validate_core_expression(expression)

def test_deep_core_tree_does_not_overflow_validation():
    expression = CoreInt(0)

    for _ in range(2000):
        expression = CorePrimOp(
            "+",
            (expression, CoreInt(1)),
        )

    validate_core_expression(expression)

def test_error_uses_nearest_available_source_span():
    source_span = SourceSpan(2, 5, 2, 15)

    expression = CoreApp(
        function=CoreVar(""),
        argument=CoreInt(1),
        span=source_span,
    )

    with pytest.raises(CoreValidationError) as error:
        validate_core_expression(expression)

    assert error.value.span == source_span
    assert str(error.value).startswith("2:5:")