
"""Integration tests for the interactive session controller."""

from dataclasses import replace

import pytest

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
    request_auto_run,
    run_interactive_batch,
    select_interactive_result_mode,
    step_interactive_session,
)
from tests.helpers.runtime_equivalence import runtime_fingerprint


def make_config(
    strategy=Strategy.CBNEED,
    *,
    policy=ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
    trace_mode=TraceMode.FULL,
):
    return ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=strategy,
        result_policy=policy,
        execution_step_limit=500,
        result_node_limit=100,
        trace_mode=trace_mode,
    )


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
@pytest.mark.parametrize("trace_mode", list(TraceMode))
def test_step_and_batch_execution_are_equivalent(
    strategy,
    trace_mode,
):
    config = make_config(strategy, trace_mode=trace_mode)
    source = "main = [1, 2]"

    stepped = create_interactive_session(source, config)
    batched = create_interactive_session(source, config)

    step_trace = []

    for _ in range(1000):
        result = step_interactive_session(stepped)
        step_trace.extend(result.trace)

        if (
            stepped.live_state.machine_state.status
            is not ExecutionStatus.RUNNING
        ):
            break
    else:
        pytest.fail("Step execution did not terminate")

    batch_result = run_interactive_batch(
        batched,
        max_steps=1000,
    )

    assert stepped.live_state.machine_state.status is (
        ExecutionStatus.COMPLETED
    )
    assert batched.live_state.machine_state.status is (
        ExecutionStatus.COMPLETED
    )

    assert (
        stepped.live_state.transition_index
        == batched.live_state.transition_index
    )

    assert runtime_fingerprint(
        stepped.live_state.machine_state
    ) == runtime_fingerprint(
        batched.live_state.machine_state
    )

    assert (
        stepped.live_state.canonical_result
        == batched.live_state.canonical_result
    )

    assert (
        stepped.live_state.instrumentation_state
        == batched.live_state.instrumentation_state
    )

    assert tuple(step_trace) == batch_result.trace

    if trace_mode is TraceMode.METRICS_ONLY:
        assert step_trace == []
        assert batch_result.trace == ()


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
def test_controller_preserves_metrics_invariants(strategy):
    session = create_interactive_session(
        "main = [1 + 2]",
        make_config(strategy),
    )

    run_interactive_batch(session, max_steps=1000)

    state = session.live_state
    machine = state.machine_state
    counters = state.instrumentation_state.counters

    assert machine.status is ExecutionStatus.COMPLETED

    assert (
        counters.evaluator_transitions
        == machine.evaluator_transition_count
    )
    assert (
        counters.evaluator_transitions
        + counters.result_consumer_transitions
        == state.transition_index
    )

    assert counters.current_heap_slots == machine.heap.current_slots
    assert counters.current_frames == machine.stack.depth
    assert counters.peak_heap_slots >= counters.current_heap_slots
    assert counters.peak_frames >= counters.current_frames


def test_manual_steps_stop_auto_run_at_terminal_state():
    session = create_interactive_session(
        "main = 42",
        make_config(policy=ResultPolicy.WHNF_ONLY),
    )

    request_auto_run(session)

    for _ in range(100):
        step_interactive_session(session)

        if (
            session.live_state.machine_state.status
            is not ExecutionStatus.RUNNING
        ):
            break
    else:
        pytest.fail("Execution did not terminate")

    assert session.live_state.machine_state.status is (
        ExecutionStatus.COMPLETED
    )
    assert not session.auto_run_requested


def test_manual_steps_stop_auto_run_when_whnf_is_pending():
    session = create_interactive_session(
        "main = 42",
        make_config(policy=ResultPolicy.ASK_AT_WHNF),
    )

    request_auto_run(session)

    for _ in range(100):
        result = step_interactive_session(session)

        if result.stop_reason is BatchStopReason.WHNF_PENDING:
            break
    else:
        pytest.fail("Execution did not reach WHNF")

    assert not session.auto_run_requested
    assert session.live_state.canonical_result is None
    assert session.live_state.machine_state.status is (
        ExecutionStatus.RUNNING
    )


def test_result_selection_does_not_implicitly_resume_play():
    session = create_interactive_session(
        "main = 42",
        make_config(policy=ResultPolicy.ASK_AT_WHNF),
    )

    result = run_interactive_batch(
        session,
        max_steps=100,
    )

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    # A pending Play request must not survive an explicit selection.
    request_auto_run(session)

    before = session.live_state.transition_index

    select_interactive_result_mode(
        session,
        ResultPolicy.WHNF_ONLY,
    )

    assert session.live_state.transition_index == before + 1
    assert not session.auto_run_requested
    assert session.live_state.canonical_result is None


def test_evaluator_budget_stops_auto_run():
    config = replace(
        make_config(),
        execution_step_limit=1,
    )

    session = create_interactive_session(
        "main = 1 + 2",
        config,
    )

    request_auto_run(session)

    result = run_interactive_batch(
        session,
        max_steps=100,
    )

    assert result.stop_reason is BatchStopReason.EVALUATOR_BUDGET
    assert not session.auto_run_requested

    assert (
        session.live_state.machine_state.evaluator_transition_count
        == 1
    )
