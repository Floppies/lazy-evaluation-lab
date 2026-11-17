
"""Tests for passive control and stack projections."""

import json
from dataclasses import replace

import pytest

from lazy_lab.core.nodes import CoreInt
from lazy_lab.runtime.control import Force, Return
from lazy_lab.runtime.environment import Environment
from lazy_lab.runtime.references import (
    HeapReference,
    ImmediateInteger,
    ObjectId,
)
from lazy_lab.runtime.stack import (
    PrimitiveOperandsFrame,
    UpdateFrame,
)
from lazy_lab.runtime.state import (
    ExecutionConfig,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.visualizer.projections import (
    project_control_and_stack,
)
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


def test_initial_control_and_empty_stack():
    state = make_state()

    projection = project_control_and_stack(state)

    assert projection["control"]["kind"] == (
        "InitializeCoreBindings"
    )

    fields = projection["control"]["fields"]

    assert fields["bindings"] == {"count": 1}
    assert fields["next_index"] == 0
    assert fields["scope_reserved"] is False
    assert fields["entry_expression"] == {
        "kind": "CoreVar"
    }

    assert projection["stack"] == {
        "depth": 0,
        "frames": [],
    }

    json.dumps(projection, allow_nan=False)


def test_force_reference_does_not_access_heap():
    state = make_state()

    reference = HeapReference(ObjectId(99))

    modified_machine = replace(
        state.machine_state,
        control=Force(reference),
    )

    modified_state = replace(
        state,
        machine_state=modified_machine,
    )

    # ObjectId 99 does not exist in the heap.
    projection = project_control_and_stack(modified_state)

    assert projection["control"] == {
        "kind": "Force",
        "fields": {
            "reference": {
                "kind": "heap",
                "object_id": 99,
            },
        },
    }

    assert modified_state.machine_state.heap.current_slots == 0


def test_stack_frames_preserve_order_and_references():
    state = make_state().snapshot()

    environment = Environment()

    state.machine_state.stack.push(
        UpdateFrame(
            thunk_reference=HeapReference(ObjectId(7)),
            return_environment=environment,
            awaiting_whnf=True,
        )
    )

    state.machine_state.stack.push(
        PrimitiveOperandsFrame(
            operator="+",
            remaining_arguments=(CoreInt(1), CoreInt(2)),
            evaluated_arguments=(ImmediateInteger(4),),
            environment=environment,
            awaiting_whnf=False,
        )
    )

    projection = project_control_and_stack(state)

    stack = projection["stack"]

    assert stack["depth"] == 2
    assert len(stack["frames"]) == 2

    bottom, top = stack["frames"]

    assert bottom["position"] == 0
    assert bottom["is_top"] is False
    assert bottom["kind"] == "UpdateFrame"

    assert bottom["fields"]["thunk_reference"] == {
        "kind": "heap",
        "object_id": 7,
    }

    assert bottom["fields"]["awaiting_whnf"] is True

    assert top["position"] == 1
    assert top["is_top"] is True
    assert top["kind"] == "PrimitiveOperandsFrame"

    assert top["fields"]["operator"] == "+"
    assert top["fields"]["remaining_arguments"] == {
        "count": 2,
    }

    assert top["fields"]["evaluated_arguments"] == {
        "count": 1,
        "references": [
            {
                "kind": "integer",
                "value": 4,
            },
        ],
    }

    json.dumps(projection, allow_nan=False)


def test_projection_is_passive_and_deterministic():
    state = make_state().snapshot()

    state = replace(
        state,
        machine_state=replace(
            state.machine_state,
            control=Return(ImmediateInteger(42)),
        ),
    )

    original = runtime_fingerprint(state)
    original_heap = state.machine_state.heap
    original_stack = state.machine_state.stack
    original_metrics = state.instrumentation_state

    first = project_control_and_stack(state)
    second = project_control_and_stack(state)

    assert first == second
    assert runtime_fingerprint(state) == original

    assert state.machine_state.heap is original_heap
    assert state.machine_state.stack is original_stack
    assert state.instrumentation_state is original_metrics

    assert first["control"]["fields"]["reference"] == {
        "kind": "integer",
        "value": 42,
    }


def test_projection_rejects_invalid_state():
    with pytest.raises(TypeError, match="ExecutionState"):
        project_control_and_stack(None)
