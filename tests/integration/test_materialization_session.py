
from dataclasses import replace

import pytest

from lazy_lab.engine.core_machine import (
    create_initial_core_state,
    run_batch,
)
from lazy_lab.engine.session_runner import run_session_batch
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.observation import (
    CanonicalConstructor,
    CanonicalInteger,
    CanonicalPartialConstructor,
    CanonicalPending,
    ConstructorWHNF,
)
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionPhase,
    ExecutionStatus,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
    InstrumentationState,
)
from lazy_lab.runtime.transitions import BatchStopReason, RuleId, TransitionKind
from tests.helpers.runtime_equivalence import runtime_fingerprint
from lazy_lab.engine.core_machine import step
from lazy_lab.engine.result_consumer import (
    select_result_mode,
    start_constructor_materialization,
    advance_constructor_materialization,
    request_materialization_field,
)
from lazy_lab.metrics.effects import StackPushed, StackPopped
from lazy_lab.metrics.reducer import reduce_metrics

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
    assert result.instrumentation_state.counters.result_nodes == 5


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
    assert result.instrumentation_state.counters.result_nodes == 2

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


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
@pytest.mark.parametrize(
    "source",
    [
        "main = 1 : 2",
        "main = 1 : (2 : 3)",
        "main = [1 : 2]",
    ],
)
def test_materialization_rejects_incompatible_cons_tail(
    strategy, source
):
    config = make_config(strategy=strategy)

    initial = create_initial_core_state(
        compile_source(source),
        config,
        session_id="invalid-cons-tail",
    )

    with pytest.raises(
        TypeError,
        match="Cons tail must evaluate to a list constructor",
    ):
        complete_in_batches(
            initial,
            config,
            batch_size=500,
        )


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
def test_whnf_observation_does_not_validate_cons_tail(strategy):
    config = make_config(
        strategy=strategy,
        policy=ResultPolicy.WHNF_ONLY,
    )

    initial = create_initial_core_state(
        compile_source("main = 1 : 2"),
        config,
        session_id="invalid-tail-whnf-only",
    )

    result, _ = complete_in_batches(
        initial,
        config,
        batch_size=500,
    )

    assert result.machine_state.status is ExecutionStatus.COMPLETED
    assert result.canonical_result == ConstructorWHNF("Cons", 2)


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
def test_result_limit_stops_before_invalid_cons_tail(strategy):
    config = replace(
        make_config(strategy=strategy),
        result_node_limit=2,
    )

    initial = create_initial_core_state(
        compile_source("main = 1 : 2"),
        config,
        session_id="invalid-tail-node-budget",
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

    assert result.canonical_result == CanonicalPartialConstructor(
        "Cons",
        (
            CanonicalInteger(1),
            CanonicalPending(),
        ),
    )

    progress = result.machine_state.result_state.materialization
    assert progress is not None
    assert progress.visited_nodes == 2


def test_materialization_stack_and_phase_accounting():
    config = make_config(Strategy.CBNEED)

    initial = create_initial_core_state(
        compile_source("main = [1 + 2]"),
        config,
        session_id="stack-phase-metrics",
    )

    # Reach the list constructor in WHNF.
    evaluated = run_batch(
        initial,
        config,
        max_steps=250,
    )

    assert evaluated.stop_reason is BatchStopReason.WHNF_PENDING

    # Begin recursive materialization.
    started = start_constructor_materialization(
        evaluated.state,
        config,
    )

    assert started.transition_kind is TransitionKind.RESULT_CONSUMER
    assert started.phase_before is ExecutionPhase.EVALUATION
    assert started.phase_after is ExecutionPhase.RESULT_MATERIALIZATION

    # Visit the Cons constructor, then encounter its
    # unevaluated head.
    visited = advance_constructor_materialization(
        started.next_state,
        config,
    )

    pending = advance_constructor_materialization(
        visited.next_state,
        config,
    )

    progress = pending.next_state.machine_state.result_state.materialization

    assert progress is not None
    assert progress.awaiting_whnf

    # The consumer requests WHNF evaluation.
    requested = request_materialization_field(
        pending.next_state,
        config,
    )

    assert requested.transition_kind is TransitionKind.RESULT_CONSUMER
    assert requested.phase_before is ExecutionPhase.RESULT_MATERIALIZATION
    assert requested.stack_effects == (
        StackPushed("MaterializationDemandFrame"),
    )

    assert requested.next_state.machine_state.stack.depth == 1
    assert pending.next_state.machine_state.stack.depth == 0

    # Account for the consumer transitions.
    metrics = InstrumentationState()

    for transition in (
        started,
        visited,
        pending,
        requested,
    ):
        metrics = reduce_metrics(metrics, transition)

    assert metrics.counters.result_consumer_transitions == 4
    assert metrics.counters.evaluator_transitions == 0
    assert metrics.counters.result_demand_evaluator_transitions == 0
    assert metrics.counters.current_frames == 1

    # Execute the field demand until the materialization
    # continuation is resumed.
    current = requested.next_state
    evaluator_steps = 0

    for _ in range(100):
        transition = step(current, config)

        assert transition.transition_kind is TransitionKind.EVALUATOR
        assert transition.phase_before is ExecutionPhase.RESULT_MATERIALIZATION

        metrics = reduce_metrics(metrics, transition)
        evaluator_steps += 1
        current = transition.next_state

        if transition.rule_id is RuleId.CORE_MATERIALIZATION_FIELD_RESUME:
            assert transition.stack_effects[-1] == (
                StackPopped("MaterializationDemandFrame")
            )
            break
    else:
        pytest.fail("Materialization demand did not resume")

    assert current.machine_state.stack.depth == 0

    counters = metrics.counters

    assert counters.current_frames == 0
    assert counters.evaluator_transitions == evaluator_steps
    assert counters.result_demand_evaluator_transitions == evaluator_steps
    assert counters.result_consumer_transitions == 4

    # The previous snapshots remain independent.
    assert pending.next_state.machine_state.stack.depth == 0
    assert requested.next_state.machine_state.stack.depth == 1


@pytest.mark.parametrize(
    ("policy", "expected_nodes"),
    [
        (ResultPolicy.WHNF_ONLY, 0),
        (ResultPolicy.MATERIALIZE_COMPLETE_VALUE, 1),
    ],
)
def test_atomic_result_node_accounting(
    policy,
    expected_nodes,
):
    config = make_config(policy=policy)

    initial = create_initial_core_state(
        compile_source("main = 42"),
        config,
        session_id="atomic-result-nodes",
    )

    completed, _ = complete_in_batches(
        initial,
        config,
        batch_size=100,
    )

    assert completed.canonical_result == CanonicalInteger(42)
    assert completed.instrumentation_state.counters.result_nodes == (
        expected_nodes
    )
