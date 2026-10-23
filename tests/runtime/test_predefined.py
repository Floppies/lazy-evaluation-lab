
"""Unit tests for predefined runtime function values."""

from dataclasses import FrozenInstanceError

import pytest

from lazy_lab.runtime.heap import HeapObject
from lazy_lab.runtime.predefined import PredefinedFunction
from lazy_lab.semantics.predefined import (
    PREDEFINED_FUNCTION_ARITIES,
    PREDEFINED_IDENTIFIERS,
)


@pytest.mark.parametrize(
    "name, expected_arity",
    list(PREDEFINED_FUNCTION_ARITIES.items()),
)
def test_predefined_function_metadata(name, expected_arity):
    function = PredefinedFunction(name)

    assert isinstance(function, HeapObject)
    assert function.name == name
    assert function.arity == expected_arity
    assert function.required_slots == 1
    assert name in PREDEFINED_IDENTIFIERS


def test_unknown_predefined_function_is_rejected():
    with pytest.raises(ValueError, match="Unknown"):
        PredefinedFunction("unknown")


def test_predefined_function_is_immutable():
    function = PredefinedFunction("seq")

    with pytest.raises(FrozenInstanceError):
        function.name = "other"
