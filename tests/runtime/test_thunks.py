
"""Structural tests for Call-by-Need thunk representations."""

from dataclasses import FrozenInstanceError

import pytest

from lazy_lab.core.nodes import (
    CoreInt,
    CorePrimOp,
    CoreVar,
    CoreApp,
    CoreBinding,
    CoreLam,
    CoreLetRec,
)
from lazy_lab.runtime.environment import Environment, UnboundNameError
from lazy_lab.runtime.references import (
    HeapReference,
    ImmediateInteger,
    ObjectId,
)
from lazy_lab.runtime.heap import Heap, Reserved, Indirection
from lazy_lab.runtime.thunks import (
    EvaluatingThunk,
    PendingThunk,
    ThunkPayload,
    capture_thunk_payload,
    allocate_thunk,
)


def test_payload_preserves_expression_and_local_captures():
    expression = CorePrimOp(
        "+",
        (CoreVar("x"), CoreInt(1)),
    )

    captured = Environment({
        "x": ImmediateInteger(20),
    })

    payload = ThunkPayload(
        expression=expression,
        captured_locals=captured,
    )

    assert payload.expression is expression
    assert payload.captured_locals is captured
    assert payload.required_slots == 2
    assert payload.captured_locals.lookup("x") == (
        ImmediateInteger(20)
    )


def test_payload_without_captures_uses_one_slot():
    payload = ThunkPayload(
        expression=CoreInt(42),
        captured_locals=Environment(),
    )

    assert payload.required_slots == 1
    assert not payload.captured_locals.bindings


def test_payload_rejects_invalid_expression():
    with pytest.raises(TypeError, match="Core expression"):
        ThunkPayload(
            expression="not-core",
            captured_locals=Environment(),
        )


def test_payload_requires_standalone_environment():
    global_environment = Environment({
        "global_value": ImmediateInteger(10),
    })

    local_environment = global_environment.extend({
        "x": ImmediateInteger(20),
    })

    with pytest.raises(ValueError, match="standalone"):
        ThunkPayload(
            expression=CoreVar("x"),
            captured_locals=local_environment,
        )


@pytest.mark.parametrize(
    "anchor_type",
    [PendingThunk, EvaluatingThunk],
)
def test_anchor_uses_one_slot_and_preserves_payload_reference(
    anchor_type,
):
    payload_reference = HeapReference(ObjectId(8))

    anchor = anchor_type(payload_reference)

    assert anchor.payload_reference is payload_reference
    assert anchor.required_slots == 1


@pytest.mark.parametrize(
    "anchor_type",
    [PendingThunk, EvaluatingThunk],
)
def test_anchor_rejects_non_heap_reference(anchor_type):
    with pytest.raises(TypeError, match="heap payload reference"):
        anchor_type(ImmediateInteger(42))


def test_payload_and_anchor_are_immutable():
    payload = ThunkPayload(
        expression=CoreInt(42),
        captured_locals=Environment(),
    )
    pending = PendingThunk(HeapReference(ObjectId(8)))
    evaluating = EvaluatingThunk(HeapReference(ObjectId(8)))

    with pytest.raises(FrozenInstanceError):
        payload.expression = CoreInt(10)

    with pytest.raises(FrozenInstanceError):
        pending.payload_reference = HeapReference(ObjectId(9))

    with pytest.raises(FrozenInstanceError):
        evaluating.payload_reference = HeapReference(ObjectId(9))


def test_payload_captures_cannot_be_mutated():
    payload = ThunkPayload(
        expression=CoreVar("x"),
        captured_locals=Environment({
            "x": ImmediateInteger(20),
        }),
    )

    with pytest.raises(TypeError):
        payload.captured_locals.bindings["x"] = (
            ImmediateInteger(99)
        )

    assert payload.captured_locals.lookup("x") == (
        ImmediateInteger(20)
    )


def test_thunk_captures_nearest_free_locals_only():
    global_env = Environment({
        "x": ImmediateInteger(100),
        "global_value": ImmediateInteger(200),
    })

    outer_x = HeapReference(ObjectId(4))
    inner_x = HeapReference(ObjectId(5))
    local_y = HeapReference(ObjectId(7))

    outer_env = global_env.extend({
        "x": outer_x,
        "unused": ImmediateInteger(99),
    })

    local_env = outer_env.extend({
        "x": inner_x,
        "y": local_y,
    })

    expression = CorePrimOp(
        "+",
        (
            CoreVar("x"),
            CorePrimOp(
                "+",
                (
                    CoreVar("y"),
                    CoreVar("global_value"),
                ),
            ),
        ),
    )

    payload = capture_thunk_payload(
        expression,
        local_env,
        global_env,
    )

    assert payload.expression is expression
    assert set(payload.captured_locals.bindings) == {
        "x", "y"
    }

    assert payload.captured_locals.lookup("x") is inner_x
    assert payload.captured_locals.lookup("y") is local_y

    assert payload.captured_locals.parent is None
    assert payload.required_slots == 3

    # Preserve the original references, not copied values.
    assert payload.captured_locals.lookup("x") is not outer_x


def test_thunk_excludes_globals_and_predefined_names():
    predefined_env = Environment({
        "seq": HeapReference(ObjectId(1)),
    })

    global_env = predefined_env.extend({
        "global_value": ImmediateInteger(100),
    })

    local_x = HeapReference(ObjectId(8))
    local_env = global_env.extend({
        "x": local_x,
    })

    expression = CoreApp(
        CoreApp(
            CoreVar("seq"),
            CoreVar("x"),
        ),
        CoreVar("global_value"),
    )

    payload = capture_thunk_payload(
        expression,
        local_env,
        global_env,
    )

    assert set(payload.captured_locals.bindings) == {"x"}
    assert payload.captured_locals.lookup("x") is local_x
    assert payload.required_slots == 2


def test_thunk_respects_nested_lambda_binders():
    global_env = Environment()
    local_ref = HeapReference(ObjectId(3))

    local_env = global_env.extend({
        "external": local_ref,
        "unused": ImmediateInteger(9),
    })

    expression = CoreLam(
        "parameter",
        CorePrimOp(
            "+",
            (
                CoreVar("parameter"),
                CoreVar("external"),
            ),
        ),
    )

    payload = capture_thunk_payload(
        expression,
        local_env,
        global_env,
    )

    assert set(payload.captured_locals.bindings) == {
        "external"
    }
    assert payload.captured_locals.lookup("external") is local_ref


def test_thunk_respects_recursive_let_bindings():
    global_env = Environment()
    external_ref = HeapReference(ObjectId(12))

    local_env = global_env.extend({
        "external": external_ref,
        "x": ImmediateInteger(999),
    })

    expression = CoreLetRec(
        bindings=(
            CoreBinding("x", CoreVar("y")),
            CoreBinding("y", CoreVar("external")),
        ),
        body=CoreVar("x"),
    )

    payload = capture_thunk_payload(
        expression,
        local_env,
        global_env,
    )

    assert set(payload.captured_locals.bindings) == {
        "external"
    }

    assert payload.captured_locals.lookup("external") is (
        external_ref
    )


def test_thunk_reconstructed_scope_preserves_shadowing():
    global_env = Environment({
        "x": ImmediateInteger(100),
        "global_value": ImmediateInteger(200),
    })

    local_x = HeapReference(ObjectId(4))

    local_env = global_env.extend({
        "x": local_x,
        "unused": ImmediateInteger(9),
    })

    payload = capture_thunk_payload(
        CorePrimOp(
            "+",
            (
                CoreVar("x"),
                CoreVar("global_value"),
            ),
        ),
        local_env,
        global_env,
    )

    reconstructed = global_env.extend(
        payload.captured_locals.bindings
    )

    assert reconstructed.lookup("x") is local_x
    assert reconstructed.lookup("global_value") == (
        ImmediateInteger(200)
    )

    assert "unused" not in reconstructed.bindings


def test_thunk_capture_rejects_unbound_name():
    global_env = Environment()
    local_env = global_env.extend({})

    with pytest.raises(UnboundNameError, match="missing"):
        capture_thunk_payload(
            CoreVar("missing"),
            local_env,
            global_env,
        )


def test_thunk_capture_requires_global_ancestor():
    global_env = Environment({
        "global_value": ImmediateInteger(1),
    })

    unrelated_env = Environment({
        "x": ImmediateInteger(2),
    })

    with pytest.raises(ValueError, match="ancestor"):
        capture_thunk_payload(
            CoreVar("x"),
            unrelated_env,
            global_env,
        )


def test_thunk_capture_handles_deep_core_expression():
    global_env = Environment()
    local_ref = HeapReference(ObjectId(9))

    local_env = global_env.extend({
        "external": local_ref,
    })

    expression = CoreVar("external")

    for _ in range(2500):
        expression = CoreApp(
            expression,
            CoreInt(1),
        )

    payload = capture_thunk_payload(
        expression,
        local_env,
        global_env,
    )

    assert payload.expression is expression
    assert payload.captured_locals.lookup("external") is (
        local_ref
    )
    assert payload.required_slots == 2


def test_allocate_fresh_thunk_creates_payload_and_anchor():
    heap = Heap()
    globals_env = Environment()
    expression = CoreInt(42)

    anchor_ref = allocate_thunk(
        heap,
        expression,
        globals_env,
        globals_env,
    )

    # Payload is allocated first, followed by the anchor.
    assert anchor_ref == HeapReference(ObjectId(1))

    anchor_cell = heap.get(anchor_ref)
    assert isinstance(anchor_cell.value, PendingThunk)
    assert anchor_cell.allocated_slots == 1

    payload_ref = anchor_cell.value.payload_reference
    payload_cell = heap.get(payload_ref)

    assert payload_ref == HeapReference(ObjectId(0))
    assert isinstance(payload_cell.value, ThunkPayload)
    assert payload_cell.value.expression is expression
    assert payload_cell.allocated_slots == 1

    assert heap.current_slots == 2
    assert heap.next_object_id == 2


def test_allocate_thunk_counts_only_local_captures():
    heap = Heap()
    local_ref = heap.allocate(Reserved(), allocated_slots=1)

    globals_env = Environment({
        "global_value": ImmediateInteger(100),
    })

    local_env = globals_env.extend({
        "x": local_ref,
        "unused": ImmediateInteger(99),
    })

    expression = CorePrimOp(
        "+",
        (CoreVar("x"), CoreVar("global_value")),
    )

    anchor_ref = allocate_thunk(
        heap,
        expression,
        local_env,
        globals_env,
    )

    anchor = heap.get(anchor_ref).value
    assert isinstance(anchor, PendingThunk)

    payload_cell = heap.get(anchor.payload_reference)
    payload = payload_cell.value

    assert isinstance(payload, ThunkPayload)
    assert set(payload.captured_locals.bindings) == {"x"}
    assert payload.captured_locals.lookup("x") is local_ref

    assert payload.required_slots == 2
    assert payload_cell.allocated_slots == 2
    assert heap.get(anchor_ref).allocated_slots == 1

    # One existing slot + two payload slots + one anchor slot.
    assert heap.current_slots == 4


def test_initialize_preallocated_recursive_anchor():
    heap = Heap()
    anchor_ref = heap.allocate(Reserved(), allocated_slots=1)

    globals_env = Environment()
    recursive_env = globals_env.extend({
        "x": anchor_ref,
    })

    returned_ref = allocate_thunk(
        heap,
        CoreVar("x"),
        recursive_env,
        globals_env,
        anchor_reference=anchor_ref,
    )

    assert returned_ref is anchor_ref
    assert returned_ref.object_id == ObjectId(0)

    anchor_cell = heap.get(anchor_ref)
    assert isinstance(anchor_cell.value, PendingThunk)
    assert anchor_cell.allocated_slots == 1

    payload_ref = anchor_cell.value.payload_reference
    payload_cell = heap.get(payload_ref)

    assert isinstance(payload_cell.value, ThunkPayload)
    assert payload_cell.value.captured_locals.lookup("x") is (
        anchor_ref
    )

    assert payload_cell.allocated_slots == 2
    assert heap.current_slots == 3
    assert heap.next_object_id == 2


def test_invalid_capture_does_not_allocate():
    heap = Heap()
    globals_env = Environment()
    local_env = globals_env.extend({})

    with pytest.raises(UnboundNameError):
        allocate_thunk(
            heap,
            CoreVar("missing"),
            local_env,
            globals_env,
        )

    assert heap.current_slots == 0
    assert heap.next_object_id == 0


def test_reject_non_reserved_preallocated_anchor():
    heap = Heap()
    globals_env = Environment()
    anchor_ref = heap.allocate(
        Indirection(ImmediateInteger(42)),
        allocated_slots=1,
    )

    before_slots = heap.current_slots
    before_id = heap.next_object_id

    with pytest.raises(ValueError, match="Reserved"):
        allocate_thunk(
            heap,
            CoreInt(7),
            globals_env,
            globals_env,
            anchor_reference=anchor_ref,
        )

    assert heap.current_slots == before_slots
    assert heap.next_object_id == before_id
    assert isinstance(heap.get(anchor_ref).value, Indirection)


def test_reject_oversized_preallocated_anchor():
    heap = Heap()
    globals_env = Environment()
    anchor_ref = heap.allocate(
        Reserved(),
        allocated_slots=3,
    )

    with pytest.raises(ValueError, match="one slot"):
        allocate_thunk(
            heap,
            CoreInt(7),
            globals_env,
            globals_env,
            anchor_reference=anchor_ref,
        )

    assert isinstance(heap.get(anchor_ref).value, Reserved)
    assert heap.current_slots == 3
    assert heap.next_object_id == 1


def test_preallocated_anchor_cannot_be_initialized_twice():
    heap = Heap()
    anchor_ref = heap.allocate(Reserved(), allocated_slots=1)
    globals_env = Environment()

    allocate_thunk(
        heap,
        CoreInt(10),
        globals_env,
        globals_env,
        anchor_reference=anchor_ref,
    )

    previous_slots = heap.current_slots
    previous_id = heap.next_object_id

    with pytest.raises(ValueError, match="Reserved"):
        allocate_thunk(
            heap,
            CoreInt(20),
            globals_env,
            globals_env,
            anchor_reference=anchor_ref,
        )

    assert heap.current_slots == previous_slots
    assert heap.next_object_id == previous_id


def test_thunk_lifecycle_preserves_historical_snapshots():
    globals_env = Environment()
    initial_heap = Heap()

    anchor_ref = allocate_thunk(
        initial_heap,
        CoreInt(42),
        globals_env,
        globals_env,
    )

    initial_cell = initial_heap.get(anchor_ref)
    pending = initial_cell.value

    assert isinstance(pending, PendingThunk)
    payload_ref = pending.payload_reference

    # Transition to EVALUATING in an isolated heap.
    evaluating_heap = initial_heap.clone()
    evaluating_heap.replace(
        anchor_ref,
        EvaluatingThunk(payload_ref),
    )

    # Transition to UPDATED in another isolated heap.
    updated_heap = evaluating_heap.clone()
    updated_heap.replace(
        anchor_ref,
        Indirection(ImmediateInteger(42)),
    )

    assert isinstance(
        initial_heap.get(anchor_ref).value,
        PendingThunk,
    )
    assert isinstance(
        evaluating_heap.get(anchor_ref).value,
        EvaluatingThunk,
    )
    assert updated_heap.get(anchor_ref).value == (
        Indirection(ImmediateInteger(42))
    )

    # Every snapshot retains the same stable address.
    for heap in (
        initial_heap,
        evaluating_heap,
        updated_heap,
    ):
        cell = heap.get(anchor_ref)

        assert cell.object_id == anchor_ref.object_id
        assert cell.allocated_slots == 1
        assert heap.current_slots == 2
        assert heap.next_object_id == 2

    # Cloning shares immutable payload objects safely.
    assert (
        initial_heap.get(payload_ref)
        is evaluating_heap.get(payload_ref)
    )
    assert (
        evaluating_heap.get(payload_ref)
        is updated_heap.get(payload_ref)
    )

    # Replacing one cell never changes an older snapshot.
    assert initial_heap.get(anchor_ref) is initial_cell


def test_multiple_local_bindings_share_thunk_identity():
    globals_env = Environment()
    initial_heap = Heap()

    anchor_ref = allocate_thunk(
        initial_heap,
        CoreInt(21),
        globals_env,
        globals_env,
    )

    local_env = globals_env.extend({
        "x": anchor_ref,
        "y": anchor_ref,
    })

    assert local_env.lookup("x") is anchor_ref
    assert local_env.lookup("y") is anchor_ref

    updated_heap = initial_heap.clone()
    updated_heap.replace(
        anchor_ref,
        Indirection(ImmediateInteger(21)),
    )

    x_cell = updated_heap.get(local_env.lookup("x"))
    y_cell = updated_heap.get(local_env.lookup("y"))

    assert x_cell is y_cell
    assert x_cell.value == Indirection(
        ImmediateInteger(21)
    )

    # The original snapshot still contains a pending thunk.
    assert isinstance(
        initial_heap.get(anchor_ref).value,
        PendingThunk,
    )


def test_indirection_aliases_preserve_original_targets():
    globals_env = Environment()
    initial_heap = Heap()

    anchor_ref = allocate_thunk(
        initial_heap,
        CoreInt(42),
        globals_env,
        globals_env,
    )

    first_alias = initial_heap.allocate(
        Indirection(anchor_ref),
        allocated_slots=1,
    )

    second_alias = initial_heap.allocate(
        Indirection(first_alias),
        allocated_slots=1,
    )

    updated_heap = initial_heap.clone()
    updated_heap.replace(
        anchor_ref,
        Indirection(ImmediateInteger(42)),
    )

    # Updating the thunk must not rewrite its aliases.
    assert updated_heap.get(first_alias).value == (
        Indirection(anchor_ref)
    )
    assert updated_heap.get(second_alias).value == (
        Indirection(first_alias)
    )

    assert updated_heap.get(anchor_ref).value == (
        Indirection(ImmediateInteger(42))
    )

    # Historical data is still unchanged.
    assert isinstance(
        initial_heap.get(anchor_ref).value,
        PendingThunk,
    )


def test_updated_anchor_retains_slots_until_gc():
    globals_env = Environment()

    local_env = globals_env.extend({
        "x": ImmediateInteger(10),
        "y": ImmediateInteger(20),
        "z": ImmediateInteger(30),
    })

    expression = CorePrimOp(
        "+",
        (
            CoreVar("x"),
            CorePrimOp(
                "+",
                (CoreVar("y"), CoreVar("z")),
            ),
        ),
    )

    initial_heap = Heap()

    anchor_ref = allocate_thunk(
        initial_heap,
        expression,
        local_env,
        globals_env,
    )

    pending = initial_heap.get(anchor_ref).value
    assert isinstance(pending, PendingThunk)

    payload_ref = pending.payload_reference
    payload_cell = initial_heap.get(payload_ref)

    assert isinstance(payload_cell.value, ThunkPayload)
    assert payload_cell.allocated_slots == 4
    assert initial_heap.get(anchor_ref).allocated_slots == 1

    # Four payload slots plus one anchor slot.
    assert initial_heap.current_slots == 5

    updated_heap = initial_heap.clone()
    updated_heap.replace(
        anchor_ref,
        Indirection(ImmediateInteger(60)),
    )

    assert updated_heap.current_slots == 5
    assert updated_heap.next_object_id == 2

    # The payload is still allocated, even though the
    # updated anchor no longer points to it.
    assert updated_heap.get(payload_ref) is payload_cell

    # Historical snapshots retain the old anchor.
    assert isinstance(
        initial_heap.get(anchor_ref).value,
        PendingThunk,
    )


def test_anchor_cannot_be_replaced_by_oversized_payload():
    globals_env = Environment()

    local_env = globals_env.extend({
        "x": ImmediateInteger(10),
    })

    heap = Heap()

    anchor_ref = allocate_thunk(
        heap,
        CoreVar("x"),
        local_env,
        globals_env,
    )

    pending = heap.get(anchor_ref).value
    assert isinstance(pending, PendingThunk)

    payload = heap.get(pending.payload_reference).value
    assert isinstance(payload, ThunkPayload)
    assert payload.required_slots == 2

    successor = heap.clone()
    original_cell = successor.get(anchor_ref)

    with pytest.raises(
        ValueError,
        match="Replacement exceeds reserved allocation size",
    ):
        successor.replace(anchor_ref, payload)

    assert successor.get(anchor_ref) is original_cell
    assert successor.get(anchor_ref).allocated_slots == 1
    assert successor.current_slots == heap.current_slots
    assert successor.next_object_id == heap.next_object_id


def test_thunk_creation_hook_uses_stable_anchor():
    heap = Heap()
    environment = Environment()
    created = []

    fresh = allocate_thunk(
        heap,
        CoreInt(10),
        environment,
        environment,
        on_created=created.append,
    )

    reserved = heap.allocate(
        Reserved(),
        allocated_slots=1,
    )

    installed = allocate_thunk(
        heap,
        CoreInt(20),
        environment,
        environment,
        anchor_reference=reserved,
        on_created=created.append,
    )

    assert created == [fresh, reserved]
    assert installed is reserved

    assert isinstance(
        heap.get(fresh).value,
        PendingThunk,
    )
    assert isinstance(
        heap.get(reserved).value,
        PendingThunk,
    )


def test_failed_thunk_installation_does_not_notify():
    heap = Heap()
    environment = Environment()
    created = []

    anchor = heap.allocate(
        Reserved(),
        allocated_slots=1,
    )

    allocate_thunk(
        heap,
        CoreInt(10),
        environment,
        environment,
        anchor_reference=anchor,
    )

    with pytest.raises(ValueError):
        allocate_thunk(
            heap,
            CoreInt(20),
            environment,
            environment,
            anchor_reference=anchor,
            on_created=created.append,
        )

    assert created == []
