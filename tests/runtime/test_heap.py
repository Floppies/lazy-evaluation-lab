
import pytest

from lazy_lab.metrics.effects import HeapAllocated, HeapReplaced
from lazy_lab.metrics.recording import HeapEffectRecorder
from lazy_lab.runtime.heap import (
    Heap,
    Indirection,
    InvalidHeapAddressError,
    Reserved,
)
from lazy_lab.runtime.references import (
    HeapReference,
    ImmediateInteger,
    ObjectId,
)


def test_allocation_assigns_stable_sequential_ids():
    heap = Heap()

    first = heap.allocate(Reserved(), allocated_slots=1)
    second = heap.allocate(Reserved(), allocated_slots=3)

    assert first == HeapReference(ObjectId(0))
    assert second == HeapReference(ObjectId(1))
    assert heap.next_object_id == 2
    assert heap.current_slots == 4


def test_replace_preserves_identity_and_slots():
    heap = Heap()

    ref = heap.allocate(Reserved(), allocated_slots=3)
    heap.replace(ref, Indirection(ImmediateInteger(42)))

    cell = heap.get(ref)

    assert cell.object_id == ref.object_id
    assert cell.allocated_slots == 3
    assert cell.value == Indirection(ImmediateInteger(42))
    assert heap.current_slots == 3
    assert heap.next_object_id == 1


def test_aliases_observe_same_updated_cell():
    heap = Heap()

    original = heap.allocate(Reserved(), allocated_slots=1)
    alias = HeapReference(original.object_id)

    heap.replace(original, Indirection(ImmediateInteger(10)))

    assert heap.get(alias).value == heap.get(original).value


def test_get_does_not_follow_indirections():
    heap = Heap()

    target = heap.allocate(Reserved(), allocated_slots=1)
    source = heap.allocate(Indirection(target), allocated_slots=1)

    assert heap.get(source).value == Indirection(target)
    assert isinstance(heap.get(target).value, Reserved)


def test_clone_preserves_previous_state():
    heap = Heap()
    ref = heap.allocate(Reserved(), allocated_slots=1)

    snapshot = heap.clone()

    heap.replace(ref, Indirection(ImmediateInteger(99)))
    new_ref = heap.allocate(Reserved(), allocated_slots=1)

    assert isinstance(snapshot.get(ref).value, Reserved)
    assert snapshot.next_object_id == 1
    assert snapshot.current_slots == 1

    assert new_ref.object_id == ObjectId(1)
    assert heap.current_slots == 2

    with pytest.raises(InvalidHeapAddressError):
        snapshot.get(new_ref)


def test_unknown_address_raises():
    heap = Heap()

    with pytest.raises(InvalidHeapAddressError):
        heap.get(HeapReference(ObjectId(99)))


@pytest.mark.parametrize("slots", [0, -1, True, 1.5])
def test_invalid_allocation_size(slots):
    heap = Heap()

    with pytest.raises(ValueError):
        heap.allocate(Reserved(), allocated_slots=slots)

    assert heap.next_object_id == 0
    assert heap.current_slots == 0


def test_heap_rejects_immediate_values():
    heap = Heap()

    with pytest.raises(TypeError):
        heap.allocate(ImmediateInteger(5), allocated_slots=1)


def test_cells_view_cannot_be_modified():
    heap = Heap()
    ref = heap.allocate(Reserved(), allocated_slots=1)

    with pytest.raises(TypeError):
        heap.cells[ref.object_id] = heap.get(ref)


def test_heap_effect_capture_is_scoped_and_not_cloned():
    heap = Heap()
    observed = []

    with heap.capture_effects(observed.append):
        cloned = heap.clone()

        # A clone must have an independent capture scope.
        with cloned.capture_effects(observed.append):
            pass

        # The same heap cannot have nested captures.
        with pytest.raises(RuntimeError):
            with heap.capture_effects(observed.append):
                pass

    # The original capture scope was correctly released.
    with heap.capture_effects(observed.append):
        pass


def test_heap_emits_allocation_and_replacement_effects():
    heap = Heap()
    recorder = HeapEffectRecorder()

    with heap.capture_effects(recorder.record):
        reference = heap.allocate(
            Reserved(),
            allocated_slots=3,
        )

        heap.replace(
            reference,
            Indirection(ImmediateInteger(42)),
        )

    effects = recorder.freeze()

    assert len(effects) == 2

    allocation, replacement = effects

    assert isinstance(allocation, HeapAllocated)
    assert allocation.object_id == reference.object_id
    assert allocation.allocated_slots == 3
    assert allocation.object_type == "Reserved"

    assert isinstance(replacement, HeapReplaced)
    assert replacement.object_id == reference.object_id
    assert replacement.previous_object_type == "Reserved"
    assert replacement.new_object_type == "Indirection"

    assert heap.current_slots == 3
    assert heap.next_object_id == 1


def test_heap_emits_only_successful_captured_operations():
    heap = Heap()
    recorder = HeapEffectRecorder()

    # No capture: no effects.
    heap.allocate(Reserved(), allocated_slots=1)
    assert recorder.freeze() == ()

    with heap.capture_effects(recorder.record):
        with pytest.raises(ValueError):
            heap.allocate(Reserved(), allocated_slots=0)

        with pytest.raises(InvalidHeapAddressError):
            heap.replace(
                HeapReference(ObjectId(99)),
                Reserved(),
            )

        reference = heap.allocate(
            Reserved(),
            allocated_slots=1,
        )

    # Capture already ended.
    heap.replace(
        reference,
        Indirection(ImmediateInteger(7)),
    )

    effects = recorder.freeze()

    assert len(effects) == 1
    assert isinstance(effects[0], HeapAllocated)
    assert effects[0].object_id == reference.object_id
