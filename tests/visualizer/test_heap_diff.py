
"""Tests for passive differences between heap snapshots."""

import json
from dataclasses import replace

import pytest

from lazy_lab.runtime.heap import Heap, Indirection, Reserved
from lazy_lab.runtime.references import ImmediateInteger
from lazy_lab.runtime.state import (
    ExecutionConfig,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.visualizer.heap_diff import (
    project_heap_snapshot_diff,
)
from lazy_lab.visualizer.session import (
    create_interactive_session,
)
from tests.helpers.runtime_equivalence import runtime_fingerprint


def make_state():
    config = ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=100,
        result_node_limit=100,
        trace_mode=TraceMode.FULL,
    )

    return create_interactive_session(
        "main = 42",
        config,
    ).live_state


def at_index(state, index):
    """Build an isolated synthetic state at a logical index."""
    return replace(
        state,
        state_id=index,
        transition_index=index,
    ).snapshot()


def test_created_and_updated_cells():
    state = make_state()
    heap = state.machine_state.heap

    original_ref = heap.allocate(
        Reserved(),
        allocated_slots=3,
    )

    previous = at_index(state, 1)

    heap.replace(
        original_ref,
        Indirection(target=ImmediateInteger(9)),
    )
    heap.allocate(Reserved(), allocated_slots=2)

    current = at_index(state, 2)

    diff = project_heap_snapshot_diff(previous, current)

    assert diff["adjacent"] is True
    assert diff["counts"] == {
        "created": 1,
        "updated": 1,
        "removed": 0,
        "unchanged": 0,
    }

    assert diff["heap_slots"] == {
        "before": 3,
        "after": 5,
        "delta": 2,
    }

    assert diff["changes"] == [
        {
            "object_id": 0,
            "change": "updated",
            "before": {
                "kind": "Reserved",
                "allocated_slots": 3,
                "required_slots": 1,
            },
            "after": {
                "kind": "Indirection",
                "allocated_slots": 3,
                "required_slots": 1,
            },
        },
        {
            "object_id": 1,
            "change": "created",
            "before": None,
            "after": {
                "kind": "Reserved",
                "allocated_slots": 2,
                "required_slots": 1,
            },
        },
    ]

    json.dumps(diff, allow_nan=False)


def test_same_kind_replacement_is_detected():
    state = make_state()
    heap = state.machine_state.heap

    reference = heap.allocate(
        Indirection(target=ImmediateInteger(3)),
        allocated_slots=1,
    )

    previous = at_index(state, 1)

    heap.replace(
        reference,
        Indirection(target=ImmediateInteger(4)),
    )

    current = at_index(state, 2)

    diff = project_heap_snapshot_diff(previous, current)

    assert diff["counts"]["updated"] == 1
    assert diff["changes"][0]["object_id"] == 0
    assert diff["changes"][0]["change"] == "updated"

    # Both versions have the same kind and size.
    assert diff["changes"][0]["before"] == (
        diff["changes"][0]["after"]
    )


def test_unchanged_snapshot_copies_do_not_report_updates():
    state = make_state()
    state.machine_state.heap.allocate(
        Reserved(),
        allocated_slots=1,
    )

    previous = at_index(state, 3)
    current = at_index(state, 5)

    diff = project_heap_snapshot_diff(previous, current)

    assert diff["adjacent"] is False
    assert diff["changes"] == []
    assert diff["counts"] == {
        "created": 0,
        "updated": 0,
        "removed": 0,
        "unchanged": 1,
    }


def test_removed_cell_is_reported_without_inferring_gc():
    state = make_state()

    state.machine_state.heap.allocate(
        Reserved(),
        allocated_slots=1,
    )

    previous = at_index(state, 1)

    # Synthetic second state with an empty heap.
    # This tests the generic diff, not a runtime GC rule.
    empty_machine = replace(
        state.machine_state,
        heap=Heap(),
    )

    empty_state = replace(
        state,
        machine_state=empty_machine,
    )

    current = at_index(empty_state, 2)

    diff = project_heap_snapshot_diff(previous, current)

    assert diff["counts"]["removed"] == 1
    assert diff["changes"][0]["change"] == "removed"
    assert diff["changes"][0]["object_id"] == 0
    assert diff["changes"][0]["after"] is None
    assert diff["heap_slots"]["delta"] == -1


def test_different_sessions_are_rejected():
    state = make_state()
    previous = at_index(state, 1)

    different = replace(
        state,
        session_id="different-session",
    )
    current = at_index(different, 2)

    with pytest.raises(ValueError, match="different sessions"):
        project_heap_snapshot_diff(previous, current)


def test_equal_or_reversed_indices_are_rejected():
    state = make_state()

    first = at_index(state, 1)
    second = at_index(state, 2)

    with pytest.raises(ValueError, match="increasing"):
        project_heap_snapshot_diff(first, first)

    with pytest.raises(ValueError, match="increasing"):
        project_heap_snapshot_diff(second, first)


def test_diff_is_passive_and_deterministic():
    state = make_state()
    heap = state.machine_state.heap

    reference = heap.allocate(
        Reserved(),
        allocated_slots=1,
    )

    previous = at_index(state, 1)

    heap.replace(
        reference,
        Indirection(target=ImmediateInteger(7)),
    )

    current = at_index(state, 2)

    previous_fingerprint = runtime_fingerprint(previous)
    current_fingerprint = runtime_fingerprint(current)

    original_previous_heap = previous.machine_state.heap
    original_current_heap = current.machine_state.heap

    first = project_heap_snapshot_diff(previous, current)
    second = project_heap_snapshot_diff(previous, current)

    assert first == second
    assert runtime_fingerprint(previous) == previous_fingerprint
    assert runtime_fingerprint(current) == current_fingerprint

    assert previous.machine_state.heap is original_previous_heap
    assert current.machine_state.heap is original_current_heap


def test_invalid_arguments_are_rejected():
    state = make_state()
    valid = at_index(state, 1)

    with pytest.raises(TypeError, match="ExecutionState"):
        project_heap_snapshot_diff(None, valid)

    with pytest.raises(TypeError, match="ExecutionState"):
        project_heap_snapshot_diff(valid, None)
