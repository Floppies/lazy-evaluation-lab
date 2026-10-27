
from dataclasses import fields

import pytest

from lazy_lab.core.nodes import CoreInt, CoreLam, CoreVar
from lazy_lab.runtime.closures import Closure
from lazy_lab.runtime.environment import Environment
from lazy_lab.runtime.global_bindings import PendingGlobal
from lazy_lab.runtime.heap import Heap, Indirection, Reserved
from lazy_lab.runtime.observation import (
    CanonicalInteger,
    CanonicalBoolean,
    OpaqueFunction,
    UnresolvedObservationError,
    observe_whnf,
)
from lazy_lab.runtime.predefined import (
    PredefinedFunction,
    PartialPredefinedFunction,
)
from lazy_lab.runtime.references import (
    ImmediateInteger,
    ImmediateBoolean,
)


@pytest.mark.parametrize(
    "reference,expected",
    [
        (ImmediateInteger(42), CanonicalInteger(42)),
        (ImmediateInteger(-7), CanonicalInteger(-7)),
        (ImmediateBoolean(True), CanonicalBoolean(True)),
        (ImmediateBoolean(False), CanonicalBoolean(False)),
    ],
)
def test_observe_immediate_values(reference, expected):
    heap = Heap()

    assert observe_whnf(heap, reference) == expected
    assert heap.current_slots == 0
    assert heap.next_object_id == 0


@pytest.mark.parametrize(
    "function",
    [
        Closure(
            CoreLam("x", CoreVar("x")),
            Environment(),
        ),
        PredefinedFunction("seq"),
        PartialPredefinedFunction(
            "seq",
            (ImmediateInteger(10),),
        ),
    ],
)
def test_observe_functions_as_opaque_values(function):
    heap = Heap()

    reference = heap.allocate(
        function,
        allocated_slots=function.required_slots,
    )

    observed = observe_whnf(heap, reference)

    assert isinstance(observed, OpaqueFunction)
    assert fields(observed) == ()

    # Observation cannot alter the existing allocation.
    assert heap.get(reference).value is function
    assert heap.current_slots == function.required_slots


@pytest.mark.parametrize(
    "value",
    [
        Reserved(),
        Indirection(ImmediateInteger(10)),
        PendingGlobal(CoreInt(10)),
    ],
)
def test_observation_rejects_unresolved_values(value):
    heap = Heap()

    reference = heap.allocate(
        value,
        allocated_slots=1,
    )

    before = dict(heap.cells)

    with pytest.raises(UnresolvedObservationError):
        observe_whnf(heap, reference)

    # The observer must neither force nor update the object.
    assert dict(heap.cells) == before
    assert heap.next_object_id == 1


def test_observation_preserves_heap_snapshot():
    heap = Heap()

    reference = heap.allocate(
        PredefinedFunction("seq"),
        allocated_slots=1,
    )

    snapshot = heap.clone()

    observed = observe_whnf(heap, reference)

    assert isinstance(observed, OpaqueFunction)
    assert dict(heap.cells) == dict(snapshot.cells)
    assert heap.current_slots == snapshot.current_slots
    assert heap.next_object_id == snapshot.next_object_id
