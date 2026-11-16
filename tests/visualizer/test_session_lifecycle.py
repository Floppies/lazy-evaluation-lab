
"""Tests for interactive session batches and lifecycle."""

import pytest

from lazy_lab.runtime.observation import CanonicalInteger
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionStatus,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.runtime.transitions import BatchStopReason
from lazy_lab.visualizer.session import (
    create_interactive_session,
    pause_interactive_session,
    request_auto_run,
    reset_interactive_session,
    run_interactive_batch,
    step_interactive_session,
)


def make_config(
    *,
    policy=ResultPolicy.ASK_AT_WHNF,
    trace_mode=TraceMode.FULL,
):
    return ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        result_policy=policy,
        execution_step_limit=200,
        result_node_limit=100,
        trace_mode=trace_mode,
    )


def test_batch_respects_requested_step_count():
    session = create_interactive_session(
        "main = 42",
        make_config(),
    )

    first = run_interactive_batch(session, max_steps=2)

    assert first.stop_reason is BatchStopReason.BATCH_LIMIT
    assert first.state is session.live_state
    assert session.live_state.transition_index == 2
    assert session.read_cursor_index == 2
    assert len(first.trace) == 2

    second = run_interactive_batch(session, max_steps=1)

    assert second.state is session.live_state
    assert session.live_state.transition_index == 3
    assert session.read_cursor_index == 3


def test_batch_preserves_historical_cursor():
    session = create_interactive_session(
        "main = 42",
        make_config(),
    )

    run_interactive_batch(session, max_steps=2)
    session.read_cursor_index = 0

    run_interactive_batch(session, max_steps=2)

    assert session.live_state.transition_index == 4
    assert session.read_cursor_index == 0


def test_pause_does_not_modify_execution_state():
    session = create_interactive_session(
        "main = 42",
        make_config(),
    )

    request_auto_run(session)
    assert session.auto_run_requested

    original_state = session.live_state
    original_cursor = session.read_cursor_index

    pause_interactive_session(session)

    assert not session.auto_run_requested
    assert session.live_state is original_state
    assert session.read_cursor_index == original_cursor

    # An explicit manual command remains available while paused.
    step_interactive_session(session)

    assert session.live_state.transition_index == 1
    assert not session.auto_run_requested


def test_batch_limit_preserves_auto_run_request():
    session = create_interactive_session(
        "main = 42",
        make_config(),
    )

    request_auto_run(session)

    result = run_interactive_batch(session, max_steps=1)

    assert result.stop_reason is BatchStopReason.BATCH_LIMIT
    assert session.auto_run_requested


def test_whnf_pending_stops_auto_run():
    session = create_interactive_session(
        "main = 42",
        make_config(),
    )

    request_auto_run(session)

    result = run_interactive_batch(session, max_steps=100)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert not session.auto_run_requested
    assert session.live_state.machine_state.status is (
        ExecutionStatus.RUNNING
    )
    assert session.live_state.canonical_result is None


def test_terminal_execution_stops_auto_run():
    session = create_interactive_session(
        "main = 42",
        make_config(policy=ResultPolicy.WHNF_ONLY),
    )

    request_auto_run(session)

    result = run_interactive_batch(session, max_steps=100)

    assert result.state.machine_state.status is (
        ExecutionStatus.COMPLETED
    )
    assert result.state.canonical_result == CanonicalInteger(42)
    assert not session.auto_run_requested

    previous = session.live_state
    repeated = run_interactive_batch(session, max_steps=1)

    assert repeated.stop_reason is BatchStopReason.TERMINAL_STATUS
    assert repeated.state is previous


def test_invalid_batch_size_preserves_session():
    session = create_interactive_session(
        "main = 42",
        make_config(),
    )

    original = session.live_state

    with pytest.raises(ValueError, match="max_steps"):
        run_interactive_batch(session, max_steps=0)

    assert session.live_state is original
    assert session.read_cursor_index == 0


def test_reset_creates_independent_run():
    session = create_interactive_session(
        "main = 42",
        make_config(trace_mode=TraceMode.EVENTS),
        capture_categories=frozenset({"thunks"}),
    )

    run_interactive_batch(session, max_steps=2)
    old_state = session.live_state
    old_id = session.session_id

    restarted = reset_interactive_session(session)

    assert restarted is not session
    assert restarted.session_id != old_id
    assert restarted.live_state.session_id == restarted.session_id

    assert restarted.live_state.transition_index == 0
    assert restarted.read_cursor_index == 0
    assert not restarted.auto_run_requested

    assert restarted.source == session.source
    assert restarted.config is session.config
    assert restarted.entry == session.entry
    assert restarted.capture_categories == session.capture_categories

    assert restarted.live_state.machine_state.heap is not (
        session.live_state.machine_state.heap
    )

    # Reset does not mutate the original run.
    assert session.live_state is old_state
    assert session.session_id == old_id
    assert session.live_state.transition_index == 2


def test_terminal_session_cannot_request_auto_run():
    session = create_interactive_session(
        "main = 42",
        make_config(policy=ResultPolicy.WHNF_ONLY),
    )

    run_interactive_batch(session, max_steps=100)

    with pytest.raises(ValueError, match="terminal session"):
        request_auto_run(session)

    assert not session.auto_run_requested
