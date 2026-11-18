
"""Tests for passive machine root projections."""

import json
from dataclasses import replace

import pytest

from lazy_lab.runtime.control import ApplyPrimitive, Force
from lazy_lab.runtime.environment import Environment
from lazy_lab.runtime.materialization import (
    MaterializationFrame,
    MaterializationState,
)
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
    ResultState,
    Strategy,
    TraceMode,
)
from lazy_lab.visualizer.heap_roots import (
    project_memory_roots,
)
from lazy_lab.visualizer.session import (
    create_interactive_session,
)
from tests.helpers.runtime_equivalence import runtime_fingerprint


def ref(object_id):
    return HeapReference(ObjectId(object_id))


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


def with_machine(state, **changes):
    return replace(
        state,
        machine_state=replace(
            state.machine_state,
            **changes,
        ),
    )


def root_map(projection):
    return {
        root["root_id"]: root["target_object_id"]
        for root in projection["roots"]
    }


def test_initial_state_has_no_heap_roots():
    projection = project_memory_roots(make_state())

    assert projection == {
        "transition_index": 0,
        "root_count": 0,
        "roots": [],
    }

    json.dumps(projection, allow_nan=False)


def test_local_and_global_environment_roots():
    state = make_state()

    local = Environment(
        {"x": ref(7)},
        parent=Environment({"outer": ref(8)}),
    )

    global_env = Environment({
        "main": ref(9),
    })

    state = with_machine(
        state,
        local_environment=local,
        global_environment=global_env,
    )

    projection = project_memory_roots(state)
    roots = root_map(projection)

    assert roots == {
        "local_environment.bindings.scope[0].x": 7,
        "local_environment.bindings.scope[1].outer": 8,
        "global_environment.bindings.scope[0].main": 9,
    }

    assert projection["root_count"] == 3


def test_two_bindings_to_same_object_are_distinct_roots():
    state = make_state()

    state = with_machine(
        state,
        local_environment=Environment({
            "x": ref(7),
            "y": ref(7),
        }),
    )

    projection = project_memory_roots(state)

    assert projection["root_count"] == 2
    assert [
        root["target_object_id"]
        for root in projection["roots"]
    ] == [7, 7]

    assert len({
        root["root_id"] for root in projection["roots"]
    }) == 2


def test_control_references_are_roots():
    state = make_state()

    state = with_machine(
        state,
        control=Force(ref(10)),
    )

    roots = root_map(project_memory_roots(state))

    assert roots == {
        "control.reference": 10,
    }

    state = with_machine(
        state,
        control=ApplyPrimitive(
            operator="+",
            arguments=(
                ImmediateInteger(1),
                ref(11),
            ),
        ),
    )

    roots = root_map(project_memory_roots(state))

    assert roots == {
        "control.arguments[1]": 11,
    }


def test_stack_references_and_saved_environments():
    state = make_state().snapshot()

    state.machine_state.stack.push(
        UpdateFrame(
            thunk_reference=ref(7),
            return_environment=Environment({
                "saved": ref(8),
            }),
        )
    )

    state.machine_state.stack.push(
        PrimitiveOperandsFrame(
            operator="+",
            remaining_arguments=(),
            evaluated_arguments=(
                ImmediateInteger(2),
                ref(9),
            ),
            environment=Environment({
                "x": ref(10),
            }),
        )
    )

    projection = project_memory_roots(state)
    roots = root_map(projection)

    assert roots == {
        "stack.frames[0].thunk_reference": 7,
        "stack.frames[0].return_environment.scope[0].saved": 8,
        "stack.frames[1].evaluated_arguments[1]": 9,
        "stack.frames[1].environment.scope[0].x": 10,
    }


def test_result_materialization_references_are_roots():
    state = make_state()

    materialization = MaterializationState(
        root_reference=ref(20),
        pending_reference=ref(21),
        frames=(
            MaterializationFrame(
                tag="Cons",
                remaining_fields=(
                    ref(22),
                    ImmediateInteger(3),
                ),
            ),
        ),
    )

    state = with_machine(
        state,
        result_state=ResultState(
            result_reference=ref(20),
            materialization=materialization,
        ),
    )

    roots = root_map(project_memory_roots(state))

    assert roots == {
        "result_state.result_reference": 20,
        "result_state.materialization.root_reference": 20,
        "result_state.materialization.pending_reference": 21,
        "result_state.materialization.frames[0].remaining_fields[0]": 22,
    }


def test_projection_does_not_dereference_heap():
    state = make_state()

    # ObjectId 999 is deliberately absent from the heap.
    state = with_machine(
        state,
        control=Force(ref(999)),
    )

    before = runtime_fingerprint(state)
    original_heap = state.machine_state.heap
    original_metrics = state.instrumentation_state

    first = project_memory_roots(state)
    second = project_memory_roots(state)

    assert first == second
    assert root_map(first) == {
        "control.reference": 999,
    }

    assert runtime_fingerprint(state) == before
    assert state.machine_state.heap is original_heap
    assert state.instrumentation_state is original_metrics

    json.dumps(first, allow_nan=False)


def test_invalid_state_is_rejected():
    with pytest.raises(TypeError, match="ExecutionState"):
        project_memory_roots(None)
