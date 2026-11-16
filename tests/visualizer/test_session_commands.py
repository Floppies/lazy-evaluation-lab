
"""Tests for interactive stepping and result selection."""

import pytest

from lazy_lab.engine.result_consumer import InvalidResultObservationError
from lazy_lab.runtime.observation import (
    CanonicalConstructor,
    CanonicalInteger,
)
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionStatus,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.runtime.transitions import BatchStopReason, RuleId
from lazy_lab.visualizer.session import (
    create_interactive_session,
    select_interactive_result_mode,
    step_interactive_session,
)


def make_config(
    strategy=Strategy.CBNEED,
    *,
    policy=ResultPolicy.ASK_AT_WHNF,
    trace_mode=TraceMode.FULL,
):
    return ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=strategy,
        result_policy=policy,
        execution_step_limit=200,
        result_node_limit=100,
        trace_mode=trace_mode,
    )


def advance_until_whnf(session):
    for _ in range(200):
        result = step_interactive_session(session)

        if result.stop_reason is BatchStopReason.WHNF_PENDING:
            return

    pytest.fail("Session did not reach WHNF")


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
@pytest.mark.parametrize(
    "trace_mode",
    [TraceMode.FULL, TraceMode.METRICS_ONLY],
)
def test_step_advances_at_most_one_transition(
    strategy,
    trace_mode,
):
    session = create_interactive_session(
        "main = 42",
        make_config(strategy, trace_mode=trace_mode),
    )

    previous = session.live_state
    result = step_interactive_session(session)

    assert result.state is session.live_state
    assert result.state.transition_index == previous.transition_index + 1
    assert result.state.state_id == previous.state_id + 1
    assert result.state.session_id == previous.session_id

    assert session.read_cursor_index == 1

    if trace_mode is TraceMode.METRICS_ONLY:
        assert result.trace == ()
    else:
        assert len(result.trace) == 1
        assert result.trace[0].previous_state_id == previous.state_id
        assert result.trace[0].next_state_id == result.state.state_id


def test_historical_cursor_does_not_rewind_execution():
    session = create_interactive_session(
        "main = 42",
        make_config(),
    )

    step_interactive_session(session)

    session.read_cursor_index = 0
    previous_live_index = session.live_state.transition_index

    step_interactive_session(session)

    assert session.live_state.transition_index == previous_live_index + 1
    assert session.read_cursor_index == 0


def test_ask_at_whnf_waits_for_explicit_selection():
    session = create_interactive_session(
        "main = 42",
        make_config(),
    )

    advance_until_whnf(session)

    waiting = session.live_state
    result = step_interactive_session(session)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert result.state is waiting
    assert result.trace == ()

    assert session.live_state is waiting
    assert waiting.canonical_result is None
    assert (
        waiting.machine_state.result_state.resolved_result_mode
        is None
    )


def test_result_selection_is_an_explicit_transition():
    session = create_interactive_session(
        "main = 42",
        make_config(),
    )

    advance_until_whnf(session)

    waiting = session.live_state
    previous_consumer_count = (
        waiting.instrumentation_state.counters.result_consumer_transitions
    )

    transition = select_interactive_result_mode(
        session,
        ResultPolicy.WHNF_ONLY,
    )

    assert transition.rule_id is RuleId.RESULT_SELECT_MODE
    assert transition.previous_state_id == waiting.state_id

    assert session.live_state is transition.next_state
    assert session.live_state.transition_index == waiting.transition_index + 1

    assert (
        session.live_state.machine_state.result_state.resolved_result_mode
        is ResultPolicy.WHNF_ONLY
    )

    assert session.live_state.canonical_result is None
    assert session.live_state.machine_state.status is ExecutionStatus.RUNNING

    assert (
        session.live_state.instrumentation_state.counters.result_consumer_transitions
        == previous_consumer_count + 1
    )


def test_invalid_selection_preserves_live_state():
    session = create_interactive_session(
        "main = 42",
        make_config(),
    )

    original = session.live_state

    with pytest.raises(InvalidResultObservationError):
        select_interactive_result_mode(
            session,
            ResultPolicy.WHNF_ONLY,
        )

    assert session.live_state is original
    assert session.read_cursor_index == 0


def test_selection_from_historical_cursor_uses_live_head():
    session = create_interactive_session(
        "main = 42",
        make_config(),
    )

    advance_until_whnf(session)

    session.read_cursor_index = 0
    live_index = session.live_state.transition_index

    select_interactive_result_mode(
        session,
        ResultPolicy.WHNF_ONLY,
    )

    assert session.live_state.transition_index == live_index + 1
    assert session.read_cursor_index == 0


def test_whnf_selection_can_complete_result():
    session = create_interactive_session(
        "main = 42",
        make_config(),
    )

    advance_until_whnf(session)

    select_interactive_result_mode(
        session,
        ResultPolicy.WHNF_ONLY,
    )

    result = step_interactive_session(session)

    assert result.state.machine_state.status is ExecutionStatus.COMPLETED
    assert result.state.canonical_result == CanonicalInteger(42)

    completed = session.live_state
    repeated = step_interactive_session(session)

    assert repeated.stop_reason is BatchStopReason.TERMINAL_STATUS
    assert repeated.state is completed
    assert repeated.trace == ()


def test_materialization_selection_uses_existing_consumer():
    session = create_interactive_session(
        "main = [1, 2]",
        make_config(),
    )

    advance_until_whnf(session)

    select_interactive_result_mode(
        session,
        ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
    )

    for _ in range(200):
        step_interactive_session(session)

        if (
            session.live_state.machine_state.status
            is not ExecutionStatus.RUNNING
        ):
            break
    else:
        pytest.fail("Materialization did not terminate")

    assert session.live_state.machine_state.status is (
        ExecutionStatus.COMPLETED
    )

    assert isinstance(
        session.live_state.canonical_result,
        CanonicalConstructor,
    )

    assert (
        session.live_state.instrumentation_state.counters.result_nodes
        == 5
    )
