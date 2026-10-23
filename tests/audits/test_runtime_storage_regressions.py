"""Behavioral regressions for the B03 storage and capture contracts."""

from dataclasses import FrozenInstanceError
from random import Random

import pytest

from lazy_lab.core.nodes import CoreInt, CoreLam, CoreVar
from lazy_lab.runtime.closures import Closure, capture_closure
from lazy_lab.runtime.environment import Environment, UnboundNameError
from lazy_lab.runtime.heap import Heap, Indirection, InvalidHeapAddressError, Reserved
from lazy_lab.runtime.references import (
    HeapReference,
    ImmediateBoolean,
    ImmediateInteger,
    ObjectId,
)
from lazy_lab.runtime.stack import (
    ApplyArgumentFrame,
    ApplyFunctionFrame,
    EmptyStackError,
    IfFrame,
    Stack,
)


class IntegerSubclass(int):
    pass


@pytest.mark.parametrize("value", [False, None, 1.0, IntegerSubclass(1)])
def test_integer_reference_requires_exact_int(value):
    with pytest.raises(TypeError):
        ImmediateInteger(value)


@pytest.mark.parametrize("value", [0, 1, None, "True"])
def test_boolean_reference_requires_exact_bool(value):
    with pytest.raises(TypeError):
        ImmediateBoolean(value)


@pytest.mark.parametrize("value", [-1, True, False, 1.0, "1", None, IntegerSubclass(1)])
def test_heap_reference_rejects_invalid_object_ids(value):
    with pytest.raises(ValueError):
        HeapReference(value)


def test_references_preserve_arbitrary_precision_and_are_frozen():
    integer = ImmediateInteger(-(10**100))
    boolean = ImmediateBoolean(False)
    reference = HeapReference(ObjectId(10**100))
    assert integer.value == -(10**100)
    for value, field in [(integer, "value"), (boolean, "value"), (reference, "object_id")]:
        with pytest.raises(FrozenInstanceError):
            setattr(value, field, 2)


@pytest.mark.parametrize("bindings,error", [
    ({"": ImmediateInteger(0)}, ValueError),
    ({1: ImmediateInteger(0)}, ValueError),
    ({"x": 1}, TypeError),
    ({"x": True}, TypeError),
    ({"x": object()}, TypeError),
])
def test_environment_rejects_invalid_bindings(bindings, error):
    with pytest.raises(error):
        Environment(bindings)


@pytest.mark.parametrize("parent", [{}, 1, object()])
def test_environment_rejects_invalid_parent(parent):
    with pytest.raises(TypeError):
        Environment(parent=parent)


def test_deep_environment_shadowing_missing_lookup_and_input_isolation():
    original = ImmediateInteger(1)
    shadow = HeapReference(ObjectId(99))
    source = {"target": original}
    root = Environment(source)
    current = root
    for index in range(4000):
        current = current.extend({"target": shadow} if index == 2000 else {})
    source.clear()
    assert root.lookup("target") is original
    assert current.lookup("target") is shadow
    with pytest.raises(UnboundNameError, match="missing"):
        current.lookup("missing")
    with pytest.raises(FrozenInstanceError):
        current.parent = None
    with pytest.raises(TypeError):
        current.bindings["target"] = original


def heap_fingerprint(heap):
    return (
        heap.next_object_id,
        heap.current_slots,
        tuple(heap.cells.items()),
    )


@pytest.mark.parametrize("slots", [0, -1, False, True, 0.5, IntegerSubclass(2)])
def test_invalid_numeric_allocation_is_atomic_on_nonempty_heap(slots):
    heap = Heap()
    heap.allocate(Reserved(), allocated_slots=3)
    before = heap_fingerprint(heap)
    with pytest.raises(ValueError):
        heap.allocate(Reserved(), allocated_slots=slots)
    assert heap_fingerprint(heap) == before


@pytest.mark.parametrize("slots", [None, "2", object()], ids=["none", "string", "opaque"])
def test_invalid_capacity_is_validated_before_comparison(slots):
    """F01: nonnumeric sizes should use the existing ValueError boundary."""
    heap = Heap()
    heap.allocate(Reserved(), allocated_slots=3)
    before = heap_fingerprint(heap)
    try:
        with pytest.raises(ValueError):
            heap.allocate(Reserved(), allocated_slots=slots)
    finally:
        assert heap_fingerprint(heap) == before


@pytest.mark.parametrize("value", [None, 1, ImmediateInteger(1), object()])
def test_invalid_heap_payload_does_not_change_storage(value):
    heap = Heap()
    reference = heap.allocate(Reserved(), allocated_slots=2)
    before = heap_fingerprint(heap)
    with pytest.raises(TypeError):
        heap.allocate(value, allocated_slots=2)
    with pytest.raises(TypeError):
        heap.replace(reference, value)
    assert heap_fingerprint(heap) == before


@pytest.mark.parametrize("reference,error", [
    (None, TypeError),
    (0, TypeError),
    (ImmediateInteger(0), TypeError),
    (HeapReference(ObjectId(99)), InvalidHeapAddressError),
])
def test_invalid_heap_reads_and_replacements_are_atomic(reference, error):
    heap = Heap()
    heap.allocate(Reserved(), allocated_slots=2)
    before = heap_fingerprint(heap)
    with pytest.raises(error):
        heap.get(reference)
    with pytest.raises(error):
        heap.replace(reference, Reserved())
    assert heap_fingerprint(heap) == before


def test_oversized_allocation_and_replacement_preserve_ids_and_capacity():
    heap = Heap()
    reference = heap.allocate(Reserved(), allocated_slots=1)
    closure = capture_closure(
        CoreLam("arg", CoreVar("x")),
        Environment({"x": reference}),
        ("x",),
    )
    before = heap_fingerprint(heap)
    with pytest.raises(ValueError):
        heap.allocate(closure, allocated_slots=1)
    with pytest.raises(ValueError):
        heap.replace(reference, closure)
    assert heap_fingerprint(heap) == before
    with pytest.raises(FrozenInstanceError):
        heap.get(reference).allocated_slots = 2
    assert heap.allocate(Reserved(), allocated_slots=1).object_id == 1


def test_heap_views_are_read_only_live_and_reads_are_passive():
    heap = Heap()
    view = heap.cells
    target = HeapReference(ObjectId(999))
    reference = heap.allocate(Indirection(target), allocated_slots=3)
    before = heap_fingerprint(heap)
    assert view[reference.object_id] is heap.get(reference)
    assert heap.get(reference).value.target is target
    assert heap_fingerprint(heap) == before
    with pytest.raises(TypeError):
        view[reference.object_id] = heap.get(reference)


def test_seeded_heap_model_preserves_slots_addresses_and_clones():
    rng = Random(20261021)
    heap = Heap()
    model = []
    for _ in range(250):
        if not model or rng.randrange(3) == 0:
            capacity = rng.randint(1, 5)
            reference = heap.allocate(Reserved(), allocated_slots=capacity)
            assert reference.object_id == len(model)
            model.append((reference, capacity))
        else:
            reference, _ = rng.choice(model)
            clone = heap.clone()
            old_cell = clone.get(reference)
            heap.replace(reference, Indirection(ImmediateInteger(rng.randint(-100, 100))))
            assert clone.get(reference) is old_cell
            assert clone.get(reference) is not heap.get(reference)
            clone.allocate(Reserved(), allocated_slots=7)
            assert clone.next_object_id == heap.next_object_id + 1
        assert heap.next_object_id == len(model)
        assert heap.current_slots == sum(capacity for _, capacity in model)
        for reference, capacity in model:
            cell = heap.get(reference)
            assert cell.object_id == reference.object_id
            assert cell.allocated_slots == capacity


def test_closure_call_scopes_keep_local_identity_and_independent_parameters():
    global_x = ImmediateInteger(100)
    local_x = HeapReference(ObjectId(7))
    globals_env = Environment({"x": global_x, "arg": ImmediateInteger(50)})
    definitions = globals_env.extend({"x": local_x, "unused": ImmediateInteger(3)})
    closure = capture_closure(CoreLam("arg", CoreVar("x")), definitions, ("x", "x"))
    first_arg, second_arg = ImmediateInteger(1), ImmediateInteger(2)
    first = closure.call_environment(first_arg, globals_env)
    second = closure.call_environment(second_arg, globals_env)
    assert closure.captured_locals.parent is None
    assert tuple(closure.captured_locals.bindings) == ("x",)
    assert first.lookup("x") is second.lookup("x") is local_x
    assert first.lookup("arg") is first_arg
    assert second.lookup("arg") is second_arg
    assert globals_env.lookup("x") is global_x
    assert first.parent is not second.parent
    with pytest.raises(UnboundNameError):
        first.lookup("unused")
    with pytest.raises(FrozenInstanceError):
        closure.captured_locals = Environment()


def test_recursive_capture_survives_heap_update_without_changing_old_clone():
    heap = Heap()
    reference = heap.allocate(Reserved(), allocated_slots=2)
    closure = capture_closure(
        CoreLam("arg", CoreVar("self")), Environment({"self": reference}), ("self",)
    )
    heap.replace(reference, closure)
    historical = heap.clone()
    result = ImmediateInteger(9)
    heap.replace(reference, Indirection(result))
    assert historical.get(reference).value is closure
    assert closure.captured_locals.lookup("self") is reference
    assert closure.call_environment(result, Environment()).lookup("self") is reference
    assert heap.get(reference).value.target is result
    assert historical.current_slots == heap.current_slots == 2
    assert historical.next_object_id == heap.next_object_id == 1


def test_missing_capture_is_explicit_and_globals_need_no_capture_slots():
    globals_env = Environment({"g": ImmediateInteger(4)})
    with pytest.raises(UnboundNameError):
        capture_closure(CoreLam("x", CoreVar("absent")), globals_env, ("absent",))
    closure = capture_closure(CoreLam("x", CoreVar("g")), globals_env, ())
    assert closure.required_slots == 1
    assert closure.call_environment(ImmediateInteger(2), globals_env).lookup("g") is globals_env.lookup("g")


@pytest.mark.parametrize("expression,captures,error", [
    (CoreInt(1), Environment(), TypeError),
    (CoreLam("x", CoreVar("x")), {}, ValueError),
    (CoreLam("x", CoreVar("x")), Environment().extend({}), ValueError),
    (CoreLam("x", CoreVar("x")), Environment({"x": ImmediateInteger(1)}), ValueError),
])
def test_invalid_direct_closure_construction(expression, captures, error):
    with pytest.raises(error):
        Closure(expression, captures)


def test_capture_helper_rejects_non_lambda():
    with pytest.raises(TypeError):
        capture_closure(CoreInt(1), Environment(), ())


def test_stack_clone_isolation_order_and_builtin_frame_immutability():
    env = Environment()
    frames = (
        ApplyFunctionFrame(CoreInt(1), env),
        IfFrame(CoreInt(2), CoreInt(3), env),
        ApplyArgumentFrame(ImmediateInteger(4)),
    )
    stack = Stack()
    for frame in frames:
        stack.push(frame)
    clone = stack.clone()
    assert all(actual is expected for actual, expected in zip(stack.frames, frames))
    for frame in reversed(frames):
        assert stack.peek() is frame
        assert stack.pop() is frame
    assert clone.depth == 3
    assert clone.pop() is frames[-1]
    assert stack.depth == 0
    with pytest.raises(EmptyStackError):
        stack.peek()
    with pytest.raises(EmptyStackError):
        stack.pop()
    with pytest.raises(TypeError):
        stack.push(object())
    with pytest.raises(FrozenInstanceError):
        frames[1].environment = Environment()
