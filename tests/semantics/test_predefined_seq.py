import pytest

from lazy_lab.ast import nodes as surface
from lazy_lab.core import nodes as core
from lazy_lab.frontend.lexer import tokenize
from lazy_lab.frontend.parser import parse_expression
from lazy_lab.frontend.tokens import TokenKind
from lazy_lab.pipeline import compile_source
from lazy_lab.semantics.name_resolution import NameResolutionError


def main_rhs(source: str) -> core.CoreExpr:
    program = compile_source(source)

    return next(
        binding.rhs
        for binding in program.bindings
        if binding.name == "main"
    )


def test_seq_is_an_ordinary_identifier():
    tokens = tokenize("seq a b")

    assert [token.kind for token in tokens] == [
        TokenKind.IDENT,
        TokenKind.IDENT,
        TokenKind.IDENT,
        TokenKind.EOF,
    ]


def test_seq_uses_ordinary_surface_application():
    expression = parse_expression("seq a b")

    assert expression == surface.Application(
        surface.Application(
            surface.Var("seq"),
            surface.Var("a"),
        ),
        surface.Var("b"),
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("main = seq", core.CoreVar("seq")),
        (
            "main = seq 1",
            core.CoreApp(
                core.CoreVar("seq"),
                core.CoreInt(1),
            ),
        ),
        (
            "main = seq 1 2",
            core.CoreApp(
                core.CoreApp(
                    core.CoreVar("seq"),
                    core.CoreInt(1),
                ),
                core.CoreInt(2),
            ),
        ),
        (
            "main = (seq 1) 2",
            core.CoreApp(
                core.CoreApp(
                    core.CoreVar("seq"),
                    core.CoreInt(1),
                ),
                core.CoreInt(2),
            ),
        ),
    ],
)
def test_seq_preserves_core_application(
    source: str,
    expected: core.CoreExpr,
):
    assert main_rhs(source) == expected


def test_seq_can_be_passed_as_a_value():
    expected = core.CoreApp(
        core.CoreLam(
            "f",
            core.CoreApp(
                core.CoreApp(
                    core.CoreVar("f"),
                    core.CoreInt(1),
                ),
                core.CoreInt(2),
            ),
        ),
        core.CoreVar("seq"),
    )

    assert main_rhs(
        r"main = (\f -> f 1 2) seq"
    ) == expected


@pytest.mark.parametrize(
    "source",
    [
        r"main = let { seq = \x y -> x } in seq 1 2",
        r"main = (\seq -> seq 1 2) (\x y -> y)",
        "seq x y = x\nmain = seq 1 2",
        "main = let { seq = seq } in seq",
    ],
)
def test_seq_may_be_shadowed(source: str):
    assert isinstance(compile_source(source), core.CoreProgram)


def test_predefined_seq_is_not_injected_into_core_bindings():
    program = compile_source("main = seq")

    assert tuple(
        binding.name for binding in program.bindings
    ) == ("main",)


@pytest.mark.parametrize(
    "source",
    [
        "main = seq missing 2",
        "main = let { x = unknown } in seq 1 2",
        "f x = 1\nf [] = seq unknown 2",
    ],
)
def test_seq_does_not_hide_undefined_names(source: str):
    with pytest.raises(
        NameResolutionError,
        match="unknown|missing",
    ):
        compile_source(source)
