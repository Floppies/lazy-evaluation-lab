
"""Unit tests for predefined runtime function values."""

from dataclasses import FrozenInstanceError

import pytest

from lazy_lab.runtime.heap import HeapObject, Heap
from lazy_lab.runtime.predefined import (
    PredefinedFunction,
    PartialPredefinedFunction,
)
from lazy_lab.runtime.references import (
    ImmediateInteger,
    HeapReference,
)
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


def test_partial_seq_metadata():
    argument = ImmediateInteger(10)

    partial = PartialPredefinedFunction(
        name="seq",
        applied_arguments=(argument,),
    )

    assert isinstance(partial, HeapObject)
    assert partial.name == "seq"
    assert partial.arity == 2
    assert partial.remaining_arity == 1
    assert partial.applied_arguments == (argument,)
    assert partial.required_slots == 2


def test_partial_seq_preserves_argument_reference():
    reference = HeapReference(7)

    partial = PartialPredefinedFunction(
        name="seq",
        applied_arguments=(reference,),
    )

    assert partial.applied_arguments[0] is reference
    assert partial.remaining_arity == 1


@pytest.mark.parametrize(
    "arguments",
    [
        (),
        (ImmediateInteger(1), ImmediateInteger(2)),
    ],
)
def test_partial_seq_rejects_invalid_arity(arguments):
    with pytest.raises(ValueError, match="Partial application"):
        PartialPredefinedFunction(
            name="seq",
            applied_arguments=arguments,
        )


def test_partial_seq_rejects_unknown_function():
    with pytest.raises(ValueError, match="Unknown"):
        PartialPredefinedFunction(
            name="missing",
            applied_arguments=(ImmediateInteger(1),),
        )


def test_partial_seq_rejects_invalid_reference():
    with pytest.raises(TypeError, match="runtime references"):
        PartialPredefinedFunction(
            name="seq",
            applied_arguments=("not-a-reference",),
        )


def test_partial_seq_requires_tuple():
    with pytest.raises(TypeError, match="tuple"):
        PartialPredefinedFunction(
            name="seq",
            applied_arguments=[ImmediateInteger(1)],
        )


def test_partial_seq_is_immutable():
    partial = PartialPredefinedFunction(
        name="seq",
        applied_arguments=(ImmediateInteger(10),),
    )

    with pytest.raises(FrozenInstanceError):
        partial.name = "other"

    with pytest.raises(FrozenInstanceError):
        partial.applied_arguments = ()


def test_partial_seq_allocates_exact_abstract_slots():
    heap = Heap()

    partial = PartialPredefinedFunction(
        name="seq",
        applied_arguments=(ImmediateInteger(10),),
    )

    reference = heap.allocate(
        partial,
        allocated_slots=partial.required_slots,
    )

    snapshot = heap.clone()

    assert heap.get(reference).value is partial
    assert heap.get(reference).allocated_slots == 2
    assert heap.current_slots == 2
    assert heap.next_object_id == 1

    assert snapshot.get(reference).value is partial
    assert snapshot.current_slots == 2

    heap.allocate(
        PredefinedFunction("seq"),
        allocated_slots=1,
    )

    assert heap.current_slots == 3
    assert snapshot.current_slots == 2
    assert snapshot.next_object_id == 1
