
from dataclasses import replace

import pytest

from lazy_lab.engine.core_machine import (
    create_initial_core_state,
    run_batch,
)
from lazy_lab.engine.result_consumer import select_result_mode
from lazy_lab.engine.session_runner import run_session_batch
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.observation import (
    CanonicalConstructor,
    CanonicalInteger,
    CanonicalPartialConstructor,
    CanonicalPending,
)
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionPhase,
    ExecutionStatus,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.runtime.transitions import BatchStopReason
from tests.helpers.runtime_equivalence import runtime_fingerprint


def make_config(
    strategy=Strategy.CBNEED,
    policy=ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
):
    return ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=strategy,
        result_policy=policy,
        execution_step_limit=500,
        result_node_limit=50,
        trace_mode=TraceMode.FULL,
    )


def complete_in_batches(state, config, batch_size):
    trace = []

    for _ in range(1000):
        batch = run_session_batch(
            state, config, max_steps=batch_size
        )
        trace.extend(batch.trace)
        state = batch.state

        if batch.stop_reason is BatchStopReason.TERMINAL_STATUS:
            return state, tuple(trace)

        assert batch.stop_reason is BatchStopReason.BATCH_LIMIT

    pytest.fail("Session failed to reach a terminal status")


def expected_list():
    return CanonicalConstructor(
        "Cons",
        (
            CanonicalInteger(1),
            CanonicalConstructor(
                "Cons",
                (
                    CanonicalInteger(2),
                    CanonicalConstructor("Nil", ()),
                ),
            ),
        ),
    )


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
def test_complete_materialization_of_finite_list(strategy):
    config = make_config(strategy)

    initial = create_initial_core_state(
        compile_source("main = [1, 2]"),
        config,
        session_id="complete-list",
    )

    result, _ = complete_in_batches(
        initial, config, batch_size=500
    )

    assert result.machine_state.status is ExecutionStatus.COMPLETED
    assert (
        result.machine_state.phase
        is ExecutionPhase.RESULT_MATERIALIZATION
    )
    assert result.machine_state.stack.depth == 0

    assert result.canonical_result == expected_list()

    progress = result.machine_state.result_state.materialization
    assert progress is not None
    assert progress.visited_nodes == 5


@pytest.mark.parametrize("mode", list(TraceMode))
def test_materialization_is_equivalent_across_batches(mode):
    config = replace(
        make_config(),
        trace_mode=mode,
    )

    initial = create_initial_core_state(
        compile_source("main = (1 + 2) : [4]"),
        config,
        session_id="materialization-batching",
    )

    uninterrupted, full_trace = complete_in_batches(
        initial,
        config,
        batch_size=500,
    )

    chunked, chunked_trace = complete_in_batches(
        initial,
        config,
        batch_size=1,
    )

    assert runtime_fingerprint(chunked) == runtime_fingerprint(
        uninterrupted
    )

    assert chunked_trace == full_trace

    if mode is TraceMode.METRICS_ONLY:
        assert full_trace == ()


def test_materialization_result_node_limit():
    config = replace(
        make_config(),
        result_node_limit=2,
    )

    initial = create_initial_core_state(
        compile_source("main = [1, 2]"),
        config,
        session_id="node-limit",
    )

    result, _ = complete_in_batches(
        initial,
        config,
        batch_size=500,
    )

    assert (
        result.machine_state.status
        is ExecutionStatus.RESULT_LIMIT_REACHED
    )

    progress = result.machine_state.result_state.materialization
    assert progress is not None
    assert progress.visited_nodes == 2

    assert result.canonical_result == CanonicalPartialConstructor(
        "Cons",
        (
            CanonicalInteger(1),
            CanonicalPending(),
        ),
    )


@pytest.mark.parametrize("extra_evaluator_steps", [0, 1])
def test_materialization_evaluator_budget_limit(
    extra_evaluator_steps,
):
    full_config = make_config()

    initial = create_initial_core_state(
        compile_source("main = (1 + 2) : []"),
        full_config,
        session_id="materialization-evaluator-limit",
    )

    root_whnf = run_batch(
        initial,
        full_config,
        max_steps=500,
    )

    assert root_whnf.stop_reason is BatchStopReason.WHNF_PENDING

    config = replace(
        full_config,
        execution_step_limit=(
            root_whnf.state.machine_state.evaluator_transition_count
            + extra_evaluator_steps
        ),
    )

    limited, _ = complete_in_batches(
        initial,
        config,
        batch_size=500,
    )

    assert (
        limited.machine_state.status
        is ExecutionStatus.STEP_LIMIT_REACHED
    )

    assert (
        limited.machine_state.evaluator_transition_count
        == config.execution_step_limit
    )

    assert limited.canonical_result == CanonicalPartialConstructor(
        "Cons",
        (CanonicalPending(),),
        unvisited_fields=1,
    )

    # A terminal state cannot perform additional work.
    repeated = run_session_batch(
        limited,
        config,
        max_steps=1,
    )

    assert repeated.stop_reason is BatchStopReason.TERMINAL_STATUS
    assert repeated.state is limited
    assert repeated.trace == ()


def test_interactive_selection_materializes_constructor():
    config = make_config(
        policy=ResultPolicy.ASK_AT_WHNF,
    )

    initial = create_initial_core_state(
        compile_source("main = [1, 2]"),
        config,
        session_id="interactive-list",
    )

    waiting = run_session_batch(
        initial,
        config,
        max_steps=500,
    )

    assert waiting.stop_reason is BatchStopReason.WHNF_PENDING
    assert waiting.state.canonical_result is None

    # Repeated calls cannot advance without an explicit selection.
    repeated = run_session_batch(
        waiting.state,
        config,
        max_steps=1,
    )

    assert repeated.state is waiting.state
    assert repeated.trace == ()
    assert repeated.stop_reason is BatchStopReason.WHNF_PENDING

    selected = select_result_mode(
        waiting.state,
        config,
        ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
    ).next_state

    result, _ = complete_in_batches(
        selected,
        config,
        batch_size=500,
    )

    assert result.machine_state.status is ExecutionStatus.COMPLETED
    assert result.canonical_result == expected_list()
