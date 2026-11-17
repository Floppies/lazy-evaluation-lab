
"""Tests for passive execution state projections."""

import json
from dataclasses import replace

import pytest

from lazy_lab.engine.result_consumer import select_result_mode
from lazy_lab.engine.session_runner import run_session_batch
from lazy_lab.runtime.state import (
    ExecutionConfig,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.runtime.transitions import BatchStopReason
from lazy_lab.visualizer.projections import (
    project_execution_overview,
)
from lazy_lab.visualizer.session import create_interactive_session
from tests.helpers.runtime_equivalence import runtime_fingerprint


def make_config(
    strategy=Strategy.CBNEED,
    *,
    trace_mode=TraceMode.FULL,
    result_policy=ResultPolicy.ASK_AT_WHNF,
):
    return ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=strategy,
        result_policy=result_policy,
        execution_step_limit=100,
        result_node_limit=50,
        trace_mode=trace_mode,
    )


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
@pytest.mark.parametrize(
    "trace_mode",
    list(TraceMode),
)
def test_initial_overview_is_json_compatible(
    strategy,
    trace_mode,
):
    config = make_config(
        strategy,
        trace_mode=trace_mode,
    )

    session = create_interactive_session(
        "main = 42",
        config,
    )

    overview = project_execution_overview(
        session.live_state,
        config,
    )

    assert overview["session_id"] == session.session_id
    assert overview["state_id"] == 0
    assert overview["transition_index"] == 0

    assert overview["config"] == {
        "machine_kind": "CORE",
        "strategy": strategy.value,
        "result_policy": "ASK_AT_WHNF",
        "execution_step_limit": 100,
        "result_node_limit": 50,
        "trace_mode": trace_mode.value,
    }

    assert overview["machine"] == {
        "status": "RUNNING",
        "phase": "INITIALIZATION",
        "control_kind": "InitializeCoreBindings",
        "evaluator_transition_count": 0,
        "stack_depth": 0,
        "heap_slots": 0,
        "heap_objects": 0,
    }

    assert overview["result"] == {
        "selected_mode": None,
        "canonical_result_available": False,
    }

    # The projection contains only JSON-compatible values.
    json.dumps(overview, allow_nan=False)


def test_projection_does_not_modify_execution_state():
    config = make_config()
    session = create_interactive_session(
        "main = let { x = 1 + 2 } in x + x",
        config,
    )

    evaluated = run_session_batch(
        session.live_state,
        config,
        max_steps=10,
    )

    state = evaluated.state

    before = runtime_fingerprint(state)
    original_heap = state.machine_state.heap
    original_stack = state.machine_state.stack
    original_metrics = state.instrumentation_state

    first = project_execution_overview(state, config)
    second = project_execution_overview(state, config)

    assert first == second
    assert runtime_fingerprint(state) == before

    assert state.machine_state.heap is original_heap
    assert state.machine_state.stack is original_stack
    assert state.instrumentation_state is original_metrics


def test_projection_does_not_select_result_mode():
    config = make_config()
    session = create_interactive_session(
        "main = 42",
        config,
    )

    waiting = run_session_batch(
        session.live_state,
        config,
        max_steps=100,
    )

    assert waiting.stop_reason is BatchStopReason.WHNF_PENDING

    overview = project_execution_overview(
        waiting.state,
        config,
    )

    assert overview["machine"]["status"] == "RUNNING"
    assert overview["result"]["selected_mode"] is None
    assert not overview["result"]["canonical_result_available"]

    assert (
        waiting.state.machine_state.result_state.resolved_result_mode
        is None
    )


def test_projection_reports_explicit_result_selection():
    config = make_config()
    session = create_interactive_session(
        "main = 42",
        config,
    )

    waiting = run_session_batch(
        session.live_state,
        config,
        max_steps=100,
    ).state

    selected = select_result_mode(
        waiting,
        config,
        ResultPolicy.WHNF_ONLY,
    ).next_state

    overview = project_execution_overview(
        selected,
        config,
    )

    assert overview["config"]["result_policy"] == "ASK_AT_WHNF"
    assert overview["result"]["selected_mode"] == "WHNF_ONLY"
    assert not overview["result"]["canonical_result_available"]


def test_projection_rejects_mismatched_configuration():
    config = make_config(Strategy.CBNEED)

    session = create_interactive_session(
        "main = 42",
        config,
    )

    other_config = replace(
        config,
        strategy=Strategy.CBV,
    )

    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        project_execution_overview(
            session.live_state,
            other_config,
        )


def test_projection_rejects_invalid_arguments():
    config = make_config()

    with pytest.raises(TypeError, match="ExecutionState"):
        project_execution_overview(None, config)

    session = create_interactive_session(
        "main = 42",
        config,
    )

    with pytest.raises(TypeError, match="ExecutionConfig"):
        project_execution_overview(
            session.live_state,
            None,
        )
