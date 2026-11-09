import pytest

from lazy_lab.runtime.constructors import ConstructorValue, allocate_constructor
from lazy_lab.runtime.heap import Heap, InvalidHeapAddressError
from lazy_lab.runtime.references import (
    ImmediateInteger,
    HeapReference,
    ObjectId,
)


def test_constructor_representation_and_slots():
    nil = ConstructorValue("Nil", ())

    cons = ConstructorValue(
        "Cons",
        (
            ImmediateInteger(1),
            HeapReference(ObjectId(0)),
        ),
    )

    assert nil.tag == "Nil"
    assert nil.fields == ()
    assert nil.required_slots == 1

    assert cons.tag == "Cons"
    assert len(cons.fields) == 2
    assert cons.required_slots == 3


def test_constructor_rejects_invalid_structure():
    with pytest.raises(ValueError):
        ConstructorValue("Tree", ())

    with pytest.raises(ValueError):
        ConstructorValue("Cons", (ImmediateInteger(1),))

    with pytest.raises(TypeError):
        ConstructorValue("Nil", [])


def test_allocate_constructor_uses_exact_slots():
    heap = Heap()

    nil_ref = allocate_constructor(heap, "Nil", ())

    cons_ref = allocate_constructor(
        heap,
        "Cons",
        (ImmediateInteger(1), nil_ref),
    )

    nil_cell = heap.get(nil_ref)
    cons_cell = heap.get(cons_ref)

    assert isinstance(nil_cell.value, ConstructorValue)
    assert isinstance(cons_cell.value, ConstructorValue)

    assert nil_cell.allocated_slots == 1
    assert cons_cell.allocated_slots == 3
    assert heap.current_slots == 4

    assert cons_cell.value.fields[1] == nil_ref
    assert nil_ref != cons_ref


def test_invalid_constructor_does_not_allocate():
    heap = Heap()

    with pytest.raises(ValueError):
        allocate_constructor(
            heap,
            "Cons",
            (ImmediateInteger(1),),
        )

    assert heap.current_slots == 0
    assert heap.next_object_id == 0
    assert len(heap.cells) == 0


def test_constructors_preserve_shared_references():
    heap = Heap()

    shared_tail = allocate_constructor(heap, "Nil", ())

    first = allocate_constructor(
        heap,
        "Cons",
        (ImmediateInteger(1), shared_tail),
    )

    second = allocate_constructor(
        heap,
        "Cons",
        (ImmediateInteger(2), shared_tail),
    )

    first_value = heap.get(first).value
    second_value = heap.get(second).value

    assert first_value.fields[1] == shared_tail
    assert second_value.fields[1] == shared_tail

    # One Nil and two Cons objects.
    assert len(heap.cells) == 3
    assert heap.current_slots == 7


def test_constructor_allocation_preserves_heap_snapshot():
    heap = Heap()

    nil_ref = allocate_constructor(heap, "Nil", ())

    snapshot = heap.clone()

    cons_ref = allocate_constructor(
        heap,
        "Cons",
        (ImmediateInteger(1), nil_ref),
    )

    assert snapshot.current_slots == 1
    assert snapshot.next_object_id == 1

    assert heap.current_slots == 4
    assert heap.next_object_id == 2

    assert snapshot.get(nil_ref).value is heap.get(nil_ref).value

    with pytest.raises(InvalidHeapAddressError):
        snapshot.get(cons_ref)