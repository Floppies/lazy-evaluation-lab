
"""Tests for passive heap memory graph projections."""

import json
from dataclasses import replace

import pytest

from lazy_lab.core.nodes import CoreInt, CoreLam, CoreVar
from lazy_lab.runtime.closures import Closure
from lazy_lab.runtime.constructors import ConstructorValue
from lazy_lab.runtime.environment import Environment
from lazy_lab.runtime.heap import Heap, Indirection, Reserved
from lazy_lab.runtime.predefined import (
    PartialPredefinedFunction,
)
from lazy_lab.runtime.references import (
    HeapReference,
    ImmediateInteger,
    ObjectId,
)
from lazy_lab.runtime.state import (
    ExecutionConfig,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.runtime.thunks import PendingThunk, ThunkPayload
from lazy_lab.visualizer.heap_graph import project_memory_graph
from lazy_lab.visualizer.session import create_interactive_session
from tests.helpers.runtime_equivalence import runtime_fingerprint


def make_state(heap=None):
    config = ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=100,
        result_node_limit=100,
        trace_mode=TraceMode.FULL,
    )

    state = create_interactive_session(
        "main = 42",
        config,
    ).live_state

    if heap is None:
        return state

    return replace(
        state,
        machine_state=replace(
            state.machine_state,
            heap=heap,
        ),
    )


def test_empty_heap_has_empty_graph():
    graph = project_memory_graph(make_state())

    assert graph == {
        "transition_index": 0,
        "nodes": [],
        "edges": [],
    }


def test_thunk_anchor_payload_and_capture_edges():
    heap = Heap()

    captured = heap.allocate(
        Reserved(),
        allocated_slots=1,
    )

    payload = ThunkPayload(
        expression=CoreInt(7),
        captured_locals=Environment({
            "x": captured,
        }),
    )

    payload_ref = heap.allocate(
        payload,
        allocated_slots=payload.required_slots,
    )

    anchor_ref = heap.allocate(
        PendingThunk(payload_ref),
        allocated_slots=1,
    )

    constructor_ref = heap.allocate(
        ConstructorValue(
            tag="Cons",
            fields=(anchor_ref, ImmediateInteger(2)),
        ),
        allocated_slots=3,
    )

    graph = project_memory_graph(make_state(heap))

    assert [node["object_id"] for node in graph["nodes"]] == [
        0, 1, 2, 3
    ]

    assert graph["edges"] == [
        {
            "source_object_id": 1,
            "target_object_id": 0,
            "role": "captured_locals.x",
        },
        {
            "source_object_id": 2,
            "target_object_id": 1,
            "role": "payload_reference",
        },
        {
            "source_object_id": 3,
            "target_object_id": 2,
            "role": "fields[0]",
        },
    ]

    assert int(constructor_ref.object_id) == 3
    json.dumps(graph, allow_nan=False)


def test_closure_and_partial_predefined_edges():
    heap = Heap()

    target = heap.allocate(Reserved(), allocated_slots=1)

    closure = Closure(
        lambda_expression=CoreLam(
            parameter="y",
            body=CoreVar("x"),
        ),
        captured_locals=Environment({
            "x": target,
            "z": ImmediateInteger(4),
        }),
    )

    heap.allocate(
        closure,
        allocated_slots=closure.required_slots,
    )

    partial = PartialPredefinedFunction(
        name="seq",
        applied_arguments=(target,),
    )

    heap.allocate(
        partial,
        allocated_slots=partial.required_slots,
    )

    graph = project_memory_graph(make_state(heap))

    assert graph["edges"] == [
        {
            "source_object_id": 1,
            "target_object_id": 0,
            "role": "captured_locals.x",
        },
        {
            "source_object_id": 2,
            "target_object_id": 0,
            "role": "applied_arguments[0]",
        },
    ]


def test_indirection_changes_edges_without_changing_node_id():
    heap = Heap()

    target = heap.allocate(Reserved(), allocated_slots=1)

    payload = heap.allocate(
        ThunkPayload(CoreInt(3), Environment()),
        allocated_slots=1,
    )

    anchor = heap.allocate(
        PendingThunk(payload),
        allocated_slots=1,
    )

    state = make_state(heap)
    before = project_memory_graph(state)

    heap.replace(
        anchor,
        Indirection(
            target=target,
            from_thunk_update=True,
        ),
    )

    after = project_memory_graph(state)

    anchor_id = int(anchor.object_id)

    before_anchor = next(
        node for node in before["nodes"]
        if node["object_id"] == anchor_id
    )

    after_anchor = next(
        node for node in after["nodes"]
        if node["object_id"] == anchor_id
    )

    assert before_anchor["kind"] == "PendingThunk"
    assert after_anchor["kind"] == "Indirection"

    assert {
        "source_object_id": anchor_id,
        "target_object_id": int(payload.object_id),
        "role": "payload_reference",
    } in before["edges"]

    assert {
        "source_object_id": anchor_id,
        "target_object_id": int(target.object_id),
        "role": "target",
    } in after["edges"]


def test_graph_does_not_dereference_missing_targets():
    heap = Heap()

    heap.allocate(
        Indirection(
            target=HeapReference(ObjectId(999)),
        ),
        allocated_slots=1,
    )

    graph = project_memory_graph(make_state(heap))

    assert len(graph["nodes"]) == 1

    assert graph["edges"] == [{
        "source_object_id": 0,
        "target_object_id": 999,
        "role": "target",
    }]

    # The graph records the actual reference, without
    # inventing a target node or dereferencing the address.


def test_graph_is_passive_and_deterministic():
    heap = Heap()
    target = heap.allocate(Reserved(), allocated_slots=1)

    heap.allocate(
        Indirection(target=target),
        allocated_slots=1,
    )

    state = make_state(heap)

    before = runtime_fingerprint(state)
    original_heap = state.machine_state.heap
    original_metrics = state.instrumentation_state

    first = project_memory_graph(state)
    second = project_memory_graph(state)

    assert first == second
    assert runtime_fingerprint(state) == before
    assert state.machine_state.heap is original_heap
    assert state.instrumentation_state is original_metrics


def test_invalid_state_is_rejected():
    with pytest.raises(TypeError, match="ExecutionState"):
        project_memory_graph(None)
