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

def test_redundant_equations_preserve_first_match():
    result = lower_source(
        "f [] = 1\n"
        "f [] = 2\n"
        "f (x:xs) = 3\n"
        "f ys = 4\n"
        "f [] = 5"
    )

    function = result.bindings[0].rhs
    assert isinstance(function, core.CoreLam)

    case = function.body
    assert isinstance(case, core.CoreCase)

    assert len(case.alternatives) == 3

    nil_alt, cons_alt, default_alt = case.alternatives

    assert isinstance(nil_alt, core.CoreConAlt)
    assert nil_alt.constructor == "Nil"
    assert nil_alt.body == core.CoreInt(1)

    assert isinstance(cons_alt, core.CoreConAlt)
    assert cons_alt.constructor == "Cons"
    assert cons_alt.body == core.CoreInt(3)

    assert isinstance(default_alt, core.CoreDefaultAlt)
    assert isinstance(default_alt.body, core.CoreLetRec)
    assert default_alt.body.body == core.CoreInt(4)

def test_first_catchall_avoids_case_and_generated_bindings():
    result = lower_source(
        "f a b = a\n"
        "f x [] = 99\n"
        "f y (h:t) = 100"
    )

    assert result.bindings[0].rhs == core.CoreLam(
        "a",
        core.CoreLam(
            "b",
            core.CoreVar("a"),
        ),
    )

def test_each_equation_binds_its_own_parameter_names():
    result = lower_source(
        "f first [] = first\n"
        "f second (head:tail) = second"
    )

    function = result.bindings[0].rhs
    assert isinstance(function, core.CoreLam)

    first_argument = function.parameter

    second_lambda = function.body
    assert isinstance(second_lambda, core.CoreLam)

    case = second_lambda.body
    assert isinstance(case, core.CoreCase)

    # Only the final argument is inspected.
    assert case.scrutinee == core.CoreVar(
        second_lambda.parameter
    )

    nil_alt, cons_alt = case.alternatives

    assert isinstance(nil_alt.body, core.CoreLetRec)
    assert nil_alt.body.bindings == (
        core.CoreBinding(
            "first",
            core.CoreVar(first_argument),
        ),
    )
    assert nil_alt.body.body == core.CoreVar("first")

    assert isinstance(cons_alt.body, core.CoreLetRec)
    assert cons_alt.body.bindings == (
        core.CoreBinding(
            "second",
            core.CoreVar(first_argument),
        ),
    )
    assert cons_alt.body.body == core.CoreVar("second")

def test_constructor_pattern_does_not_inspect_fields():
    result = lower_source(
        "f (head:tail) = 10"
    )

    function = result.bindings[0].rhs
    assert isinstance(function, core.CoreLam)

    case = function.body
    assert isinstance(case, core.CoreCase)

    assert len(case.alternatives) == 1

    alternative = case.alternatives[0]

    assert isinstance(alternative, core.CoreConAlt)
    assert alternative.constructor == "Cons"
    assert alternative.binders == ("head", "tail")
    assert alternative.body == core.CoreInt(10)

def test_non_exhaustive_matching_is_preserved():
    result = lower_source("f [] = 0")

    function = result.bindings[0].rhs
    assert isinstance(function, core.CoreLam)

    case = function.body
    assert isinstance(case, core.CoreCase)

    assert len(case.alternatives) == 1
    assert isinstance(
        case.alternatives[0],
        core.CoreConAlt,
    )
    assert case.alternatives[0].constructor == "Nil"

def test_equations_after_fallback_are_unreachable():
    result = lower_source(
        "f [] = 0\n"
        "f x = x\n"
        "f (h:t) = 99"
    )

    function = result.bindings[0].rhs
    assert isinstance(function, core.CoreLam)

    case = function.body
    assert isinstance(case, core.CoreCase)

    assert len(case.alternatives) == 2
    assert isinstance(case.alternatives[0], core.CoreConAlt)
    assert isinstance(case.alternatives[1], core.CoreDefaultAlt)

def test_pattern_matching_full_program_integration():
    source = (
        "length [] = 0\n"
        "length (x:xs) = 1 + length xs\n"
        "main = let { values = [1, 2, 3] } in length values"
    )

    result = lower_source(source)

    assert len(result.bindings) == 2
    assert [binding.name for binding in result.bindings] == [
        "length",
        "main",
    ]

    length_function = result.bindings[0].rhs
    assert isinstance(length_function, core.CoreLam)
    assert isinstance(length_function.body, core.CoreCase)

    main_expression = result.bindings[1].rhs
    assert isinstance(main_expression, core.CoreLetRec)

    values_binding = main_expression.bindings[0]
    assert values_binding.name == "values"
    assert isinstance(values_binding.rhs, core.CoreCon)
    assert values_binding.rhs.constructor == "Cons"

    assert isinstance(main_expression.body, core.CoreApp)

def test_pattern_alternatives_preserve_source_spans():
    source = (
        "f [] = 0\n"
        "f (head:tail) = head"
    )

    surface_program = parse_program(source)
    validate_program(surface_program)

    result = lower_program(surface_program)

    function = result.bindings[0].rhs
    assert isinstance(function, core.CoreLam)

    case = function.body
    assert isinstance(case, core.CoreCase)

    first_equation, second_equation = surface_program.definitions

    assert function.span == first_equation.span

    assert (
        case.alternatives[0].span
        == first_equation.parameters[-1].span
    )

    assert (
        case.alternatives[1].span
        == second_equation.parameters[-1].span
    )

