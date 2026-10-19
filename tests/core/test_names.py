from lazy_lab.core.names import FreshNameSupply
from lazy_lab.frontend.lexer import tokenize
from lazy_lab.frontend.tokens import TokenKind
from lazy_lab.frontend.errors import LexerError
from lazy_lab.core import nodes as core
from lazy_lab.core.validation import validate_core_expression


def test_fresh_names_are_unique():
    names = FreshNameSupply()

    assert names.fresh("arg") == "$arg0"
    assert names.fresh("arg") == "$arg1"
    assert names.fresh("arg") == "$arg2"


def test_prefix_counters_are_independent():
    names = FreshNameSupply()

    assert names.fresh("arg") == "$arg0"
    assert names.fresh("match") == "$match0"
    assert names.fresh("arg") == "$arg1"
    assert names.fresh("match") == "$match1"


def test_separate_supplies_are_deterministic():
    first = FreshNameSupply()
    second = FreshNameSupply()

    assert first.fresh("arg") == second.fresh("arg")
    assert first.fresh("match") == second.fresh("match")

def test_reserved_names_are_skipped():
    names = FreshNameSupply(
        reserved={"$arg0", "$arg1", "$match0"}
    )

    assert names.fresh("arg") == "$arg2"
    assert names.fresh("match") == "$match1"


def test_reserving_name_after_generation():
    names = FreshNameSupply()

    assert names.fresh("arg") == "$arg0"

    names.reserve("$arg2")

    assert names.fresh("arg") == "$arg1"
    assert names.fresh("arg") == "$arg3"


def test_duplicate_reservations_are_allowed():
    names = FreshNameSupply()

    names.reserve("$arg0")
    names.reserve("$arg0")

    assert names.fresh("arg") == "$arg1"

import pytest


@pytest.mark.parametrize(
    "prefix",
    [
        "",
        "Arg",
        "123",
        "$arg",
        "arg-name",
        "arg name",
        None,
        42,
    ],
)
def test_invalid_prefix_is_rejected(prefix):
    names = FreshNameSupply()

    with pytest.raises(ValueError, match="Invalid fresh-name prefix"):
        names.fresh(prefix)


@pytest.mark.parametrize(
    "name",
    [
        "",
        "$",
        "$Arg0",
        "Invalid",
        "if",
        "x-y",
        None,
        42,
    ],
)
def test_invalid_reserved_identifier_is_rejected(name):
    names = FreshNameSupply()

    with pytest.raises(ValueError, match="Invalid Core identifier"):
        names.reserve(name)

def test_generated_names_cannot_be_written_in_surface():
    with pytest.raises(LexerError):
        tokenize("$arg0")


def test_generated_names_do_not_collide_with_surface_identifiers():
    source = "let { arg0 = 1; match0 = arg0 } in match0"

    source_names = {
        token.lexeme
        for token in tokenize(source)
        if token.kind == TokenKind.IDENT
    }

    names = FreshNameSupply(reserved=source_names)

    generated = {
        names.fresh("arg"),
        names.fresh("match"),
    }

    assert generated.isdisjoint(source_names)
    assert generated == {"$arg0", "$match0"}

def test_generated_name_is_valid_core_binder():
    names = FreshNameSupply()
    parameter = names.fresh("arg")

    expression = core.CoreLam(
        parameter=parameter,
        body=core.CoreVar(parameter),
    )

    validate_core_expression(expression)