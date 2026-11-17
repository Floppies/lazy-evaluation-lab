
"""Tests for synchronized interactive session projections."""

import json

import pytest

from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionStatus,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.visualizer.session import (
    create_interactive_session,
    follow_live_head,
    run_interactive_batch,
    select_historical_state,
)
from lazy_lab.visualizer.session_projection import (
    project_interactive_session,
)
from tests.helpers.runtime_equivalence import runtime_fingerprint


def make_config(
    *,
    strategy=Strategy.CBNEED,
    trace_mode=TraceMode.FULL,
):
    return ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=strategy,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=500,
        result_node_limit=100,
        trace_mode=trace_mode,
    )


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
@pytest.mark.parametrize("mode", list(TraceMode))
def test_initial_session_projection_is_synchronized(
    strategy,
    mode,
):
    session = create_interactive_session(
        "main = 42",
        make_config(strategy=strategy, trace_mode=mode),
    )

    projection = project_interactive_session(session)

    assert projection["navigation"] == {
        "session_id": session.session_id,
        "read_cursor_index": 0,
        "live_transition_index": 0,
        "following_live_head": True,
        "available_indices": [0],
        "auto_run_requested": False,
        "trace_mode": mode.value,
    }

    assert projection["execution"]["transition_index"] == 0
    assert projection["execution"]["machine"]["status"] == "RUNNING"
    assert projection["control_stack"]["stack"]["depth"] == 0

    assert (
        projection["metrics_result"]["metrics"]["counters"][
            "evaluator_transitions"
        ] == 0
    )

    assert projection["metrics_result"]["result"]["canonical"] is None

    json.dumps(projection, allow_nan=False)


def test_historical_projection_uses_selected_snapshot():
    session = create_interactive_session(
        "main = let { x = 1 + 2 } in x + x",
        make_config(),
    )

    run_interactive_batch(session, max_steps=3)

    live_before = session.live_state
    fingerprint_before = runtime_fingerprint(live_before)

    select_historical_state(session, 0)

    projection = project_interactive_session(session)

    assert projection["navigation"]["read_cursor_index"] == 0
    assert projection["navigation"]["live_transition_index"] == 3
    assert not projection["navigation"]["following_live_head"]

    assert projection["execution"]["transition_index"] == 0
    assert projection["execution"]["machine"]["phase"] == "INITIALIZATION"

    assert (
        projection["metrics_result"]["metrics"]["counters"][
            "evaluator_transitions"
        ] == 0
    )

    assert session.live_state is live_before
    assert runtime_fingerprint(session.live_state) == fingerprint_before
    assert session.read_cursor_index == 0


def test_execution_from_historical_cursor_does_not_change_inspection():
    session = create_interactive_session(
        "main = let { x = 1 + 2 } in x + x",
        make_config(),
    )

    run_interactive_batch(session, max_steps=3)
    select_historical_state(session, 0)

    run_interactive_batch(session, max_steps=2)

    projection = project_interactive_session(session)

    assert projection["navigation"]["read_cursor_index"] == 0
    assert projection["navigation"]["live_transition_index"] == 5
    assert projection["execution"]["transition_index"] == 0
    assert session.live_state.transition_index == 5

    follow_live_head(session)

    live_projection = project_interactive_session(session)

    assert live_projection["navigation"]["following_live_head"]
    assert live_projection["execution"]["transition_index"] == 5
    assert (
        live_projection["metrics_result"]["metrics"]["counters"][
            "evaluator_transitions"
        ] > 0
    )


def test_events_projection_uses_retained_history():
    session = create_interactive_session(
        "main = let { x = 1 + 2 } in x + x",
        make_config(trace_mode=TraceMode.EVENTS),
        capture_categories=frozenset({"thunks"}),
    )

    run_interactive_batch(session, max_steps=500)

    assert session.live_state.machine_state.status is (
        ExecutionStatus.COMPLETED
    )

    assert session.history.available_indices

    historical_index = min(session.history.available_indices)

    select_historical_state(session, historical_index)

    projection = project_interactive_session(session)

    assert projection["navigation"]["trace_mode"] == "EVENTS"
    assert (
        projection["navigation"]["read_cursor_index"]
        == historical_index
    )
    assert (
        projection["execution"]["transition_index"]
        == historical_index
    )

    assert projection["navigation"]["available_indices"] == sorted(
        set(session.history.available_indices)
        | {session.live_state.transition_index}
    )

    json.dumps(projection, allow_nan=False)


def test_metrics_only_projects_live_state_without_history():
    session = create_interactive_session(
        "main = 42",
        make_config(trace_mode=TraceMode.METRICS_ONLY),
    )

    run_interactive_batch(session, max_steps=500)

    projection = project_interactive_session(session)

    live_index = session.live_state.transition_index

    assert session.history.snapshot_count == 0
    assert projection["navigation"]["available_indices"] == [
        live_index
    ]
    assert projection["navigation"]["following_live_head"]

    assert projection["execution"]["transition_index"] == live_index
    assert projection["metrics_result"]["result"]["canonical"] == {
        "kind": "integer",
        "value": 42,
    }


def test_session_projection_is_passive():
    session = create_interactive_session(
        "main = [1, 2]",
        make_config(),
    )

    run_interactive_batch(session, max_steps=20)

    before = runtime_fingerprint(session.live_state)
    cursor_before = session.read_cursor_index
    history_count = session.history.snapshot_count

    first = project_interactive_session(session)
    second = project_interactive_session(session)

    assert first == second
    assert runtime_fingerprint(session.live_state) == before
    assert session.read_cursor_index == cursor_before
    assert session.history.snapshot_count == history_count


def test_projection_rejects_invalid_session():
    with pytest.raises(TypeError, match="InteractiveSession"):
        project_interactive_session(None)
