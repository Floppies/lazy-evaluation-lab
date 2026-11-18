
"""Integration tests for synchronized memory projections."""

import json

import pytest

from lazy_lab.runtime.state import (
    ExecutionConfig,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.visualizer.heap_diff import project_heap_snapshot_diff
from lazy_lab.visualizer.session import (
    create_interactive_session,
    follow_live_head,
    get_inspected_state,
    run_interactive_batch,
    select_historical_state,
)
from lazy_lab.visualizer.session_projection import (
    project_interactive_session,
)
from tests.helpers.runtime_equivalence import runtime_fingerprint


SOURCE = "main = let { x = 1 + 2 } in x + x"


def make_session(mode=TraceMode.FULL, categories=frozenset()):
    config = ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=500,
        result_node_limit=100,
        trace_mode=mode,
    )

    return create_interactive_session(
        SOURCE,
        config,
        capture_categories=categories,
    )


@pytest.mark.parametrize("mode", list(TraceMode))
def test_initial_memory_projection(mode):
    session = make_session(mode)

    projection = project_interactive_session(session)
    memory = projection["memory"]

    assert memory["heap_table"]["transition_index"] == 0
    assert memory["heap_graph"]["transition_index"] == 0
    assert memory["roots"]["transition_index"] == 0

    assert memory["heap_table"]["cells"] == []
    assert memory["heap_graph"]["nodes"] == []
    assert memory["heap_graph"]["edges"] == []
    assert memory["roots"]["roots"] == []

    assert memory["diff"] == {
        "available": False,
        "reason": "initial_state",
        "comparison": None,
    }

    json.dumps(projection, allow_nan=False)


def test_full_history_projects_memory_and_adjacent_diff():
    session = make_session()

    run_interactive_batch(session, max_steps=10)

    projection = project_interactive_session(session)
    memory = projection["memory"]

    index = session.live_state.transition_index

    assert index > 0

    for section in ("heap_table", "heap_graph", "roots"):
        assert memory[section]["transition_index"] == index

    table_ids = {
        cell["object_id"]
        for cell in memory["heap_table"]["cells"]
    }

    graph_ids = {
        node["object_id"]
        for node in memory["heap_graph"]["nodes"]
    }

    assert table_ids == graph_ids
    assert memory["heap_table"]["object_count"] == len(table_ids)

    assert memory["diff"]["available"] is True
    assert memory["diff"]["reason"] is None

    comparison = memory["diff"]["comparison"]

    assert comparison["from_transition_index"] == index - 1
    assert comparison["to_transition_index"] == index
    assert comparison["adjacent"] is True

    json.dumps(projection, allow_nan=False)


def test_historical_memory_uses_selected_snapshot():
    session = make_session()

    run_interactive_batch(session, max_steps=15)

    live_before = session.live_state
    fingerprint_before = runtime_fingerprint(live_before)
    live_index = live_before.transition_index

    historical_index = 4
    select_historical_state(session, historical_index)

    inspected = get_inspected_state(session)
    previous = session.history.get_snapshot(historical_index - 1)

    expected_diff = project_heap_snapshot_diff(
        previous,
        inspected,
    )

    projection = project_interactive_session(session)

    assert projection["navigation"]["read_cursor_index"] == 4
    assert (
        projection["navigation"]["live_transition_index"]
        == live_index
    )

    assert projection["memory"]["heap_table"][
        "transition_index"
    ] == 4

    assert projection["memory"]["heap_graph"][
        "transition_index"
    ] == 4

    assert projection["memory"]["diff"]["comparison"] == (
        expected_diff
    )

    assert session.live_state is live_before
    assert runtime_fingerprint(session.live_state) == fingerprint_before

    follow_live_head(session)

    current = project_interactive_session(session)

    assert current["memory"]["heap_table"][
        "transition_index"
    ] == live_index


def test_events_without_captures_has_no_previous_snapshot():
    session = make_session(TraceMode.EVENTS)

    run_interactive_batch(session, max_steps=10)

    projection = project_interactive_session(session)

    assert session.history.snapshot_count == 0
    assert projection["memory"]["diff"] == {
        "available": False,
        "reason": "previous_state_not_retained",
        "comparison": None,
    }

    assert projection["memory"]["heap_table"]["transition_index"] == (
        session.live_state.transition_index
    )


def test_events_with_retained_adjacent_states():
    session = make_session(
        TraceMode.EVENTS,
        frozenset({"thunks"}),
    )

    run_interactive_batch(session, max_steps=500)

    available = set(session.history.available_indices)

    candidates = sorted(
        index
        for index in available
        if index > 0 and index - 1 in available
    )

    assert candidates, "Expected an adjacent captured event window"

    selected_index = candidates[0]

    select_historical_state(session, selected_index)

    projection = project_interactive_session(session)
    diff = projection["memory"]["diff"]

    assert diff["available"] is True
    assert diff["comparison"]["from_transition_index"] == (
        selected_index - 1
    )
    assert diff["comparison"]["to_transition_index"] == (
        selected_index
    )
    assert diff["comparison"]["adjacent"] is True


def test_metrics_only_does_not_invent_history():
    session = make_session(TraceMode.METRICS_ONLY)

    run_interactive_batch(session, max_steps=10)

    projection = project_interactive_session(session)

    assert session.history.snapshot_count == 0

    assert projection["memory"]["diff"] == {
        "available": False,
        "reason": "previous_state_not_retained",
        "comparison": None,
    }

    assert projection["memory"]["heap_table"]["cells"]
    assert projection["memory"]["heap_graph"]["nodes"]


def test_memory_projection_is_passive_and_deterministic():
    session = make_session()

    run_interactive_batch(session, max_steps=12)

    state_before = runtime_fingerprint(session.live_state)
    cursor_before = session.read_cursor_index
    history_before = session.history.snapshot_count

    first = project_interactive_session(session)
    second = project_interactive_session(session)

    assert first == second
    assert runtime_fingerprint(session.live_state) == state_before
    assert session.read_cursor_index == cursor_before
    assert session.history.snapshot_count == history_before

    json.dumps(first, allow_nan=False)
