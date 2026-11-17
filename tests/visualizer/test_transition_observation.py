
"""Tests for passive transition observation hooks."""

import pytest

from lazy_lab.engine.core_machine import (
    create_initial_core_state,
    run_batch,
)
from lazy_lab.engine.session_runner import run_session_batch
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionStatus,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.runtime.transitions import (
    BatchStopReason,
    TraceEntry,
    TransitionKind,
)
from tests.helpers.runtime_equivalence import runtime_fingerprint


def make_config(
    *,
    trace_mode=TraceMode.FULL,
    result_policy=ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
):
    return ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        result_policy=result_policy,
        execution_step_limit=500,
        result_node_limit=100,
        trace_mode=trace_mode,
    )


def make_initial_state(source, config):
    return create_initial_core_state(
        compile_source(source),
        config,
        session_id="observation-test",
    )


@pytest.mark.parametrize("trace_mode", list(TraceMode))
def test_session_observer_receives_every_transition(trace_mode):
    config = make_config(trace_mode=trace_mode)
    initial = make_initial_state("main = [1, 2]", config)

    observed = []

    result = run_session_batch(
        initial,
        config,
        max_steps=500,
        on_transition=lambda before, transition: observed.append(
            (before, transition)
        ),
    )

    assert result.state.machine_state.status is (
        ExecutionStatus.COMPLETED
    )

    assert len(observed) == (
        result.state.transition_index - initial.transition_index
    )

    for index, (before, transition) in enumerate(observed):
        assert transition.previous_state_id == before.state_id
        assert (
            transition.next_state.transition_index
            == before.transition_index + 1
        )

        if index > 0:
            assert before is observed[index - 1][1].next_state

    assert any(
        transition.transition_kind is TransitionKind.EVALUATOR
        for _, transition in observed
    )
    assert any(
        transition.transition_kind is TransitionKind.RESULT_CONSUMER
        for _, transition in observed
    )

    if trace_mode is TraceMode.METRICS_ONLY:
        assert result.trace == ()
    else:
        assert result.trace == tuple(
            TraceEntry.from_transition(transition)
            for _, transition in observed
        )


def test_observation_does_not_change_execution():
    config = make_config()
    initial = make_initial_state(
        "main = (1 + 2) : [4]",
        config,
    )

    observed = []

    with_observer = run_session_batch(
        initial,
        config,
        max_steps=500,
        on_transition=lambda before, transition: observed.append(
            (before, transition)
        ),
    )

    without_observer = run_session_batch(
        initial,
        config,
        max_steps=500,
    )

    assert with_observer.stop_reason == without_observer.stop_reason
    assert with_observer.trace == without_observer.trace

    assert runtime_fingerprint(
        with_observer.state
    ) == runtime_fingerprint(
        without_observer.state
    )

    assert observed


def test_core_batch_observer_receives_evaluator_transitions():
    config = make_config()
    initial = make_initial_state("main = 42", config)

    observed = []

    result = run_batch(
        initial,
        config,
        max_steps=100,
        on_transition=lambda before, transition: observed.append(
            (before, transition)
        ),
    )

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert len(observed) == len(result.trace)
    assert observed[0][0] is initial

    assert all(
        transition.transition_kind is TransitionKind.EVALUATOR
        for _, transition in observed
    )


def test_no_observation_when_waiting_for_result_selection():
    config = make_config(
        result_policy=ResultPolicy.ASK_AT_WHNF,
    )
    initial = make_initial_state("main = 42", config)

    waiting = run_session_batch(
        initial,
        config,
        max_steps=100,
    )

    assert waiting.stop_reason is BatchStopReason.WHNF_PENDING

    observed = []

    repeated = run_session_batch(
        waiting.state,
        config,
        max_steps=10,
        on_transition=lambda before, transition: observed.append(
            (before, transition)
        ),
    )

    assert repeated.stop_reason is BatchStopReason.WHNF_PENDING
    assert repeated.state is waiting.state
    assert observed == []
