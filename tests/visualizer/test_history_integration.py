
"""Integration tests for session history and navigation."""

import pytest

from lazy_lab.runtime.heap import Reserved
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionStatus,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.runtime.transitions import BatchStopReason
from lazy_lab.visualizer.history import HistoryStateUnavailableError
from lazy_lab.visualizer.session import (
    available_session_indices,
    create_interactive_session,
    follow_live_head,
    get_inspected_state,
    pause_interactive_session,
    request_auto_run,
    reset_interactive_session,
    run_interactive_batch,
    select_historical_state,
    select_interactive_result_mode,
    update_interactive_capture_categories,
)


def make_config(
    trace_mode=TraceMode.FULL,
    *,
    policy=ResultPolicy.WHNF_ONLY,
):
    return ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        result_policy=policy,
        execution_step_limit=500,
        result_node_limit=100,
        trace_mode=trace_mode,
    )


@pytest.mark.parametrize("mode", list(TraceMode))
def test_initial_history_respects_trace_mode(mode):
    session = create_interactive_session(
        "main = 42",
        make_config(mode),
    )

    if mode is TraceMode.FULL:
        assert session.history.available_indices == (0,)
        assert session.event_capture is None

    elif mode is TraceMode.EVENTS:
        assert session.history.available_indices == ()
        assert session.event_capture is not None

    else:
        assert session.history.available_indices == ()
        assert session.event_capture is None

    assert available_session_indices(session) == (0,)


def test_full_history_retains_every_transition():
    session = create_interactive_session(
        "main = [1, 2]",
        make_config(),
    )

    result = run_interactive_batch(
        session,
        max_steps=500,
    )

    assert result.state.machine_state.status is (
        ExecutionStatus.COMPLETED
    )

    count = session.live_state.transition_index

    assert session.history.available_indices == tuple(
        range(count + 1)
    )
    assert session.history.snapshot_count == count + 1
    assert session.live_state is result.state


def test_explicit_result_selection_is_retained():
    session = create_interactive_session(
        "main = 42",
        make_config(
            policy=ResultPolicy.ASK_AT_WHNF,
        ),
    )

    waiting = run_interactive_batch(
        session,
        max_steps=500,
    )

    assert waiting.stop_reason is BatchStopReason.WHNF_PENDING

    previous_index = session.live_state.transition_index

    transition = select_interactive_result_mode(
        session,
        ResultPolicy.WHNF_ONLY,
    )

    selected_index = previous_index + 1

    assert transition.next_state is session.live_state
    assert session.live_state.transition_index == selected_index
    assert selected_index in session.history.available_indices

    selected_snapshot = session.history.get_snapshot(
        selected_index
    )

    assert (
        selected_snapshot.machine_state.result_state.resolved_result_mode
        is ResultPolicy.WHNF_ONLY
    )

    run_interactive_batch(session, max_steps=10)

    assert session.live_state.machine_state.status is (
        ExecutionStatus.COMPLETED
    )


def test_events_history_captures_real_thunk_windows():
    session = create_interactive_session(
        "main = let { x = 1 + 2 } in x + x",
        make_config(TraceMode.EVENTS),
        capture_categories=frozenset({"thunks"}),
    )

    result = run_interactive_batch(
        session,
        max_steps=500,
    )

    assert result.state.machine_state.status is (
        ExecutionStatus.COMPLETED
    )

    capture = session.event_capture
    assert capture is not None

    assert capture.captured_event_indices

    available = set(session.history.available_indices)
    final_index = session.live_state.transition_index

    for event_index in capture.captured_event_indices:
        assert event_index - 1 in available
        assert event_index in available

        if event_index + 1 <= final_index:
            assert event_index + 1 in available

    assert all(
        capture.capture_reasons[index] == frozenset({"thunks"})
        for index in capture.captured_event_indices
    )


def test_events_selection_preserves_observer_continuity():
    session = create_interactive_session(
        "main = [1, 2]",
        make_config(
            TraceMode.EVENTS,
            policy=ResultPolicy.ASK_AT_WHNF,
        ),
        capture_categories=frozenset({"materialization"}),
    )

    waiting = run_interactive_batch(
        session,
        max_steps=500,
    )

    assert waiting.stop_reason is BatchStopReason.WHNF_PENDING

    select_interactive_result_mode(
        session,
        ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
    )

    result = run_interactive_batch(
        session,
        max_steps=500,
    )

    assert result.state.machine_state.status is (
        ExecutionStatus.COMPLETED
    )

    capture = session.event_capture
    assert capture is not None
    assert capture.captured_event_indices


def test_navigation_is_passive_and_preserves_live_head():
    session = create_interactive_session(
        "main = 42",
        make_config(),
    )

    run_interactive_batch(session, max_steps=2)

    live = session.live_state
    metrics = live.instrumentation_state
    live_index = live.transition_index

    historical = select_historical_state(session, 0)

    assert session.read_cursor_index == 0
    assert session.live_state is live
    assert session.live_state.transition_index == live_index
    assert session.live_state.instrumentation_state is metrics

    historical.machine_state.heap.allocate(
        Reserved(),
        allocated_slots=1,
    )

    inspected_again = get_inspected_state(session)

    assert inspected_again.transition_index == 0
    assert inspected_again.machine_state.heap.current_slots == 0

    current = follow_live_head(session)

    assert session.read_cursor_index == live_index
    assert current.transition_index == live_index
    assert session.live_state is live


@pytest.mark.parametrize(
    "mode",
    [TraceMode.EVENTS, TraceMode.METRICS_ONLY],
)
def test_unavailable_history_does_not_move_cursor(mode):
    session = create_interactive_session(
        "main = 42",
        make_config(mode),
    )

    run_interactive_batch(session, max_steps=1)

    live_index = session.live_state.transition_index
    assert session.read_cursor_index == live_index

    with pytest.raises(HistoryStateUnavailableError):
        select_historical_state(session, 0)

    assert session.read_cursor_index == live_index

    # Live state remains available in every trace mode.
    assert get_inspected_state(session).transition_index == live_index


def test_filter_updates_require_pause():
    session = create_interactive_session(
        "main = 42",
        make_config(TraceMode.EVENTS),
        capture_categories=frozenset({"thunks"}),
    )

    request_auto_run(session)

    with pytest.raises(RuntimeError, match="Pause"):
        update_interactive_capture_categories(
            session,
            frozenset({"heap"}),
        )

    assert session.capture_categories == frozenset({"thunks"})

    pause_interactive_session(session)

    update_interactive_capture_categories(
        session,
        frozenset({"heap"}),
    )

    assert session.capture_categories == frozenset({"heap"})
    assert session.event_capture is not None
    assert session.event_capture.selected_categories == frozenset({
        "heap"
    })


def test_reset_creates_fresh_history():
    session = create_interactive_session(
        "main = 42",
        make_config(),
    )

    run_interactive_batch(session, max_steps=3)

    original_id = session.session_id
    original_count = session.history.snapshot_count

    restarted = reset_interactive_session(session)

    assert restarted.session_id != original_id
    assert restarted.history.snapshot_count == 1
    assert restarted.history.available_indices == (0,)
    assert restarted.live_state.transition_index == 0

    assert session.history.snapshot_count == original_count
    assert session.live_state.transition_index == 3
