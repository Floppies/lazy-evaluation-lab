
"""Tests for passive simulated heap table projections."""

import json
from dataclasses import replace

import pytest

from lazy_lab.core.nodes import CoreInt, CoreLam, CoreVar
from lazy_lab.runtime.closures import Closure
from lazy_lab.runtime.constructors import ConstructorValue
from lazy_lab.runtime.environment import Environment
from lazy_lab.runtime.global_bindings import PendingGlobal
from lazy_lab.runtime.heap import Heap, Indirection, Reserved
from lazy_lab.runtime.predefined import (
    PredefinedFunction,
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
from lazy_lab.runtime.thunks import (
    EvaluatingThunk,
    PendingThunk,
    ThunkPayload,
)
from lazy_lab.visualizer.heap_table import project_heap_table
from lazy_lab.visualizer.session import create_interactive_session
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


def with_heap(state, heap):
    return replace(
        state,
        machine_state=replace(
            state.machine_state,
            heap=heap,
        ),
    )


def test_empty_heap_projection():
    state = make_state()

    projection = project_heap_table(state)

    assert projection == {
        "transition_index": 0,
        "object_count": 0,
        "current_slots": 0,
        "next_object_id": 0,
        "cells": [],
    }

    json.dumps(projection, allow_nan=False)


def test_thunk_anchor_and_payload_are_separate_cells():
    heap = Heap()

    payload = ThunkPayload(
        expression=CoreInt(7),
        captured_locals=Environment({
            "z": ImmediateInteger(9),
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

    projection = project_heap_table(
        with_heap(make_state(), heap)
    )

    assert projection["object_count"] == 2
    assert projection["current_slots"] == 3

    payload_row, anchor_row = projection["cells"]

    assert payload_row == {
        "object_id": int(payload_ref.object_id),
        "kind": "ThunkPayload",
        "allocated_slots": 2,
        "required_slots": 2,
        "details": {
            "expression_kind": "CoreInt",
            "captured_local_names": ["z"],
        },
    }

    assert anchor_row == {
        "object_id": int(anchor_ref.object_id),
        "kind": "PendingThunk",
        "allocated_slots": 1,
        "required_slots": 1,
        "details": {
            "payload_reference": {
                "kind": "heap",
                "object_id": int(payload_ref.object_id),
            },
        },
    }


def test_anchor_updates_preserve_object_identity():
    heap = Heap()

    payload_ref = heap.allocate(
        ThunkPayload(CoreInt(3), Environment()),
        allocated_slots=1,
    )
    anchor_ref = heap.allocate(
        PendingThunk(payload_ref),
        allocated_slots=1,
    )

    state = with_heap(make_state(), heap)

    pending = project_heap_table(state)

    heap.replace(
        anchor_ref,
        EvaluatingThunk(payload_ref),
    )

    evaluating = project_heap_table(state)

    heap.replace(
        anchor_ref,
        Indirection(
            target=ImmediateInteger(3),
            from_thunk_update=True,
        ),
    )

    updated = project_heap_table(state)

    anchor_id = int(anchor_ref.object_id)

    def anchor_row(projection):
        return next(
            row for row in projection["cells"]
            if row["object_id"] == anchor_id
        )

    assert anchor_row(pending)["kind"] == "PendingThunk"
    assert anchor_row(evaluating)["kind"] == "EvaluatingThunk"
    assert anchor_row(updated)["kind"] == "Indirection"

    assert anchor_row(updated)["details"] == {
        "target": {
            "kind": "integer",
            "value": 3,
        },
        "from_thunk_update": True,
    }

    assert all(
        anchor_row(projection)["allocated_slots"] == 1
        for projection in (pending, evaluating, updated)
    )

    assert updated["current_slots"] == 2


def test_constructor_and_indirection_do_not_follow_references():
    heap = Heap()

    heap.allocate(
        ConstructorValue(
            tag="Cons",
            fields=(
                ImmediateInteger(1),
                HeapReference(ObjectId(999)),
            ),
        ),
        allocated_slots=3,
    )

    heap.allocate(
        Indirection(
            target=HeapReference(ObjectId(999)),
        ),
        allocated_slots=1,
    )

    projection = project_heap_table(
        with_heap(make_state(), heap)
    )

    constructor, indirection = projection["cells"]

    assert constructor["kind"] == "ConstructorValue"
    assert constructor["details"] == {
        "tag": "Cons",
        "arity": 2,
        "fields": [
            {"kind": "integer", "value": 1},
            {"kind": "heap", "object_id": 999},
        ],
    }

    assert indirection["details"]["target"] == {
        "kind": "heap",
        "object_id": 999,
    }

    # This test intentionally contains references that do not
    # exist in the heap. A passive table does not dereference them.
    json.dumps(projection, allow_nan=False)


def test_remaining_supported_object_kinds():
    heap = Heap()

    objects = [
        Reserved(),
        PendingGlobal(CoreInt(1)),
        Closure(
            lambda_expression=CoreLam(
                parameter="x",
                body=CoreVar("x"),
            ),
            captured_locals=Environment(),
        ),
        PredefinedFunction("seq"),
        PartialPredefinedFunction(
            name="seq",
            applied_arguments=(ImmediateInteger(1),),
        ),
    ]

    for value in objects:
        heap.allocate(
            value,
            allocated_slots=value.required_slots,
        )

    projection = project_heap_table(
        with_heap(make_state(), heap)
    )

    assert [
        row["kind"] for row in projection["cells"]
    ] == [
        "Reserved",
        "PendingGlobal",
        "Closure",
        "PredefinedFunction",
        "PartialPredefinedFunction",
    ]

    assert projection["cells"][1]["details"] == {
        "expression_kind": "CoreInt",
    }

    assert projection["cells"][2]["details"] == {
        "parameter": "x",
        "captured_local_names": [],
    }

    assert projection["cells"][4]["details"] == {
        "name": "seq",
        "arity": 2,
        "remaining_arity": 1,
        "applied_arguments": [
            {"kind": "integer", "value": 1},
        ],
    }


def test_heap_projection_is_passive_and_deterministic():
    heap = Heap()
    heap.allocate(Reserved(), allocated_slots=3)

    state = with_heap(make_state(), heap)

    before = runtime_fingerprint(state)
    heap_before = state.machine_state.heap
    metrics_before = state.instrumentation_state

    first = project_heap_table(state)
    second = project_heap_table(state)

    assert first == second
    assert runtime_fingerprint(state) == before

    assert state.machine_state.heap is heap_before
    assert state.instrumentation_state is metrics_before
    assert first["current_slots"] == 3
    assert first["cells"][0]["required_slots"] == 1


def test_invalid_state_is_rejected():
    with pytest.raises(TypeError, match="ExecutionState"):
        project_heap_table(None)
