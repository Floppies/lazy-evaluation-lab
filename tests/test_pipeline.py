import pytest

from lazy_lab.pipeline import compile_source
from lazy_lab.core import nodes as core
from lazy_lab.semantics.name_resolution import NameResolutionError


@pytest.mark.parametrize(
    "source",
    [
        "main = 42",
        "main = double 10\ndouble x = x * 2",
        "main = let { x = y; y = 10 } in x",
        "main = let { x = x } in 10",
        "main = let { x = 10; f x = x; g = x } in f g",
        (
            "length [] = 0\n"
            "length (x:xs) = 1 + length xs\n"
            "main = length [1, 2, 3]"
        ),
    ],
)
def test_valid_source_compiles(source):
    result = compile_source(source)

    assert isinstance(result, core.CoreProgram)
    assert len(result.bindings) > 0

def test_pipeline_rejects_unknown_name_in_unreachable_equation():
    source = (
        "f x = 10\n"
        "f [] = unknown"
    )

    with pytest.raises(
        NameResolutionError,
        match="unknown",
    ) as error:
        compile_source(source)

    assert error.value.span is not None
    assert error.value.span.start_line == 2

def test_pipeline_rejects_leaked_local_parameter():
    source = (
        "main = let { "
        "f x = x; "
        "g = x "
        "} in g"
    )

    with pytest.raises(
        NameResolutionError,
        match="x",
    ):
        compile_source(source)

def test_undefined_name_reports_correct_location():
    with pytest.raises(NameResolutionError) as error:
        compile_source("main = missing")

    span = error.value.span

    assert span is not None
    assert span.start_line == 1
    assert span.start_column == 8

    assert str(error.value).startswith(
        "1:8: Undefined identifier: missing"
    )