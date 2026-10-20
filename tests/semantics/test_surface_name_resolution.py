import pytest

from lazy_lab.frontend.parser import parse_program
from lazy_lab.ast.validation import validate_program
from lazy_lab.semantics.name_resolution import (
    NameResolutionError,
    check_surface_names,
)


def check_source(source: str) -> None:
    program = parse_program(source)
    validate_program(program)
    check_surface_names(program)

@pytest.mark.parametrize(
    "source",
    [
        "main = 42",
        "main = double 10\ndouble x = x * 2",
        "x = 10\nmain = let { x = 20 } in x",
        "main = (\\x -> x + 1) 10",
        "main = (\\x -> (\\x -> x) x) 1",
        "main = let { x = y; y = 10 } in x",
        "main = let { x = x } in 10",
        (
            "even n = if n == 0 then True else odd (n - 1)\n"
            "odd n = if n == 0 then False else even (n - 1)"
        ),
        (
            "f x [] = x\n"
            "f y (head:tail) = y"
        ),
    ],
)
def test_valid_lexical_references(source):
    check_source(source)

@pytest.mark.parametrize(
    "source",
    [
        "main = unknown",
        "main = 1 + missing",
        "main = if False then missing else 10",
        "main = let { x = missing } in 10",
        "f x = x\nmain = x",
        "f (head:tail) = missing",
        "f x [] = x\nf y (h:t) = x",
    ],
)
def test_undefined_references_are_rejected(source):
    with pytest.raises(NameResolutionError):
        check_source(source)

def test_unreachable_equation_is_still_name_checked():
    source = (
        "f x = 10\n"
        "f [] = unknown"
    )

    with pytest.raises(
        NameResolutionError,
        match="unknown",
    ) as error:
        check_source(source)

    assert error.value.span is not None
    assert error.value.span.start_line == 2

def test_function_parameter_does_not_escape_scope():
    source = (
        "f x = x\n"
        "main = x"
    )

    with pytest.raises(
        NameResolutionError,
        match="x",
    ):
        check_source(source)

def test_shadowing_in_local_functions():
    source = (
        "main = let { "
        "x = 10; "
        "f x = x; "
        "g = x "
        "} in f g"
    )

    check_source(source)

def test_lambda_parameter_does_not_escape():
    source = (
        "main = let { "
        "f = \\x -> x; "
        "g = x "
        "} in g"
    )

    with pytest.raises(
        NameResolutionError,
        match="x",
    ):
        check_source(source)

def test_unreachable_constructor_equation_is_checked():
    source = (
        "f [] = 1\n"
        "f [] = missing\n"
        "f (x:xs) = 2"
    )

    with pytest.raises(
        NameResolutionError,
        match="missing",
    ):
        check_source(source)

def test_deep_expression_name_checking():
    source = (
        "x = 1\n"
        "main = " + " + ".join(["x"] * 2000)
    )

    check_source(source)
