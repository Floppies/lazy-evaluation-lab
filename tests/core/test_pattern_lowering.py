from lazy_lab.ast.validation import validate_program
from lazy_lab.frontend.parser import parse_program

from lazy_lab.core import nodes as core
from lazy_lab.core.desugar import lower_program
from lazy_lab.core.validation import validate_core_program


def lower_source(source: str) -> core.CoreProgram:
    surface_program = parse_program(source)
    validate_program(surface_program)

    result = lower_program(surface_program)
    validate_core_program(result)

    return result

def test_constructor_equations_lower_to_case():
    result = lower_source(
        "length [] = 0\n"
        "length (x:xs) = 1 + length xs"
    )

    assert len(result.bindings) == 1

    function = result.bindings[0].rhs

    assert isinstance(function, core.CoreLam)
    assert isinstance(function.body, core.CoreCase)

    case = function.body

    assert case.scrutinee == core.CoreVar(
        function.parameter
    )

    assert [
        alternative.constructor
        for alternative in case.alternatives
    ] == ["Nil", "Cons"]

def test_variable_pattern_first_does_not_force_argument():
    result = lower_source(
        "f x = 10\n"
        "f [] = 20"
    )

    function = result.bindings[0].rhs

    assert isinstance(function, core.CoreLam)
    assert function.body == core.CoreInt(10)

def test_variable_fallback_after_constructor():
    result = lower_source(
        "f [] = 0\n"
        "f xs = 1"
    )

    function = result.bindings[0].rhs

    assert isinstance(function, core.CoreLam)
    assert isinstance(function.body, core.CoreCase)

    alternatives = function.body.alternatives

    assert len(alternatives) == 2
    assert isinstance(alternatives[0], core.CoreConAlt)
    assert isinstance(alternatives[1], core.CoreDefaultAlt)

def test_duplicate_constructor_equations_use_first_match():
    result = lower_source(
        "f [] = 1\n"
        "f [] = 2"
    )

    function = result.bindings[0].rhs

    assert isinstance(function, core.CoreLam)
    assert isinstance(function.body, core.CoreCase)

    alternatives = function.body.alternatives

    assert len(alternatives) == 1
    assert isinstance(alternatives[0], core.CoreConAlt)
    assert alternatives[0].body == core.CoreInt(1)

def test_only_final_argument_is_pattern_matched():
    result = lower_source(
        "f x [] = x\n"
        "f y (h:t) = y"
    )

    function = result.bindings[0].rhs

    assert isinstance(function, core.CoreLam)

    second_lambda = function.body
    assert isinstance(second_lambda, core.CoreLam)

    case = second_lambda.body
    assert isinstance(case, core.CoreCase)

    assert case.scrutinee == core.CoreVar(
        second_lambda.parameter
    )

def test_multiple_variable_equations_keep_first_match():
    result = lower_source(
        "f x = 1\n"
        "f y = 2"
    )

    assert len(result.bindings) == 1

    function = result.bindings[0].rhs

    assert function == core.CoreLam(
        "x",
        core.CoreInt(1),
    )

def test_default_fallback_uses_original_argument():
    result = lower_source(
        "f [] = 0\n"
        "f xs = xs"
    )

    function = result.bindings[0].rhs

    assert isinstance(function, core.CoreLam)

    case = function.body
    assert isinstance(case, core.CoreCase)

    default = case.alternatives[-1]
    assert isinstance(default, core.CoreDefaultAlt)
    assert isinstance(default.body, core.CoreLetRec)

    binding = default.body.bindings[0]

    assert binding.name == "xs"
    assert binding.rhs == core.CoreVar(
        function.parameter
    )

    assert default.binder != function.parameter

def test_fresh_names_are_unique_across_functions():
    result = lower_source(
        "f [] = 0\n"
        "g [] = 1"
    )

    f = result.bindings[0].rhs
    g = result.bindings[1].rhs

    assert isinstance(f, core.CoreLam)
    assert isinstance(g, core.CoreLam)

    assert f.parameter != g.parameter

def test_pattern_lowering_is_deterministic():
    source = (
        "f [] = 0\n"
        "f (x:xs) = x\n"
        "f ys = ys"
    )

    first = lower_source(source)
    second = lower_source(source)

    assert first == second