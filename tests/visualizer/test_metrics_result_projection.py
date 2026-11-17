
"""Tests for passive metrics and canonical-result projections."""

import json
from dataclasses import asdict, replace

import pytest

from lazy_lab.engine.session_runner import run_session_batch
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionStatus,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.visualizer.projections import (
    project_metrics_and_result,
)
from lazy_lab.visualizer.session import create_interactive_session
from tests.helpers.runtime_equivalence import runtime_fingerprint


def make_config(
    *,
    strategy=Strategy.CBNEED,
    policy=ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
    result_node_limit=100,
):
    return ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=strategy,
        result_policy=policy,
        execution_step_limit=500,
        result_node_limit=result_node_limit,
        trace_mode=TraceMode.FULL,
    )


def execute(source, config):
    session = create_interactive_session(source, config)

    batch = run_session_batch(
        session.live_state,
        config,
        max_steps=1000,
    )

    return batch.state


def test_initial_metrics_and_result():
    config = make_config()
    session = create_interactive_session("main = 42", config)

    projection = project_metrics_and_result(session.live_state)

    counters = session.live_state.instrumentation_state.counters

    assert projection["metrics"]["counters"] == asdict(counters)
    assert projection["metrics"]["baseline_slots"] is None

    assert projection["metrics"]["derived"] == {
        "semantic_reductions": 0,
        "current_frames": 0,
        "thunks_never_forced": 0,
        "additional_peak_over_baseline": None,
    }

    assert projection["result"] == {
        "available": False,
        "canonical": None,
    }

    json.dumps(projection, allow_nan=False)


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
def test_accumulated_metrics_match_runtime_state(strategy):
    config = make_config(strategy=strategy)

    state = execute(
        "main = let { x = 1 + 2 } in x + x",
        config,
    )

    assert state.machine_state.status is ExecutionStatus.COMPLETED

    projection = project_metrics_and_result(state)

    counters = state.instrumentation_state.counters
    instrumentation = state.instrumentation_state

    assert projection["metrics"]["counters"] == asdict(counters)

    assert (
        projection["metrics"]["derived"]["semantic_reductions"]
        == counters.semantic_reductions
    )

    assert (
        projection["metrics"]["derived"]["current_frames"]
        == counters.current_frames
    )

    assert (
        projection["metrics"]["derived"]["thunks_never_forced"]
        == counters.thunks_never_forced
    )

    assert (
        projection["metrics"]["derived"]["additional_peak_over_baseline"]
        == instrumentation.additional_peak_over_baseline
    )

    assert (
        counters.evaluator_transitions
        + counters.result_consumer_transitions
        == state.transition_index
    )


def test_materialized_list_is_projected_without_evaluation():
    state = execute("main = [1, 2]", make_config())

    assert state.machine_state.status is ExecutionStatus.COMPLETED

    before = runtime_fingerprint(state)

    projection = project_metrics_and_result(state)

    assert projection["result"] == {
        "available": True,
        "canonical": {
            "kind": "constructor",
            "tag": "Cons",
            "fields": [
                {
                    "kind": "integer",
                    "value": 1,
                },
                {
                    "kind": "constructor",
                    "tag": "Cons",
                    "fields": [
                        {
                            "kind": "integer",
                            "value": 2,
                        },
                        {
                            "kind": "constructor",
                            "tag": "Nil",
                            "fields": [],
                        },
                    ],
                },
            ],
        },
    }

    assert runtime_fingerprint(state) == before
    json.dumps(projection, allow_nan=False)


def test_whnf_constructor_preserves_observation_boundary():
    config = make_config(policy=ResultPolicy.WHNF_ONLY)

    state = execute("main = [1, 2]", config)

    projection = project_metrics_and_result(state)

    assert projection["result"] == {
        "available": True,
        "canonical": {
            "kind": "constructor_whnf",
            "tag": "Cons",
            "arity": 2,
        },
    }

    assert projection["metrics"]["counters"]["result_nodes"] == 0


def test_partial_materialization_is_preserved():
    config = make_config(result_node_limit=2)

    state = execute("main = [1, 2]", config)

    assert state.machine_state.status is (
        ExecutionStatus.RESULT_LIMIT_REACHED
    )

    projection = project_metrics_and_result(state)

    assert projection["result"]["available"] is True
    assert projection["result"]["canonical"] == {
        "kind": "partial_constructor",
        "tag": "Cons",
        "fields": [
            {"kind": "integer", "value": 1},
            {"kind": "pending"},
        ],
        "unvisited_fields": 0,
    }

    assert projection["metrics"]["counters"]["result_nodes"] == 2


def test_opaque_function_is_not_expanded():
    state = execute(
        r"main = \x -> x",
        make_config(),
    )

    projection = project_metrics_and_result(state)

    assert projection["result"] == {
        "available": True,
        "canonical": {
            "kind": "opaque_function",
        },
    }


def test_projection_is_passive_and_deterministic():
    state = execute(
        "main = [1 + 2]",
        make_config(),
    )

    before = runtime_fingerprint(state)
    original_heap = state.machine_state.heap
    original_stack = state.machine_state.stack
    original_metrics = state.instrumentation_state

    first = project_metrics_and_result(state)
    second = project_metrics_and_result(state)

    assert first == second
    assert runtime_fingerprint(state) == before

    assert state.machine_state.heap is original_heap
    assert state.machine_state.stack is original_stack
    assert state.instrumentation_state is original_metrics


def test_projection_rejects_invalid_state():
    with pytest.raises(TypeError, match="ExecutionState"):
        project_metrics_and_result(None)
