
import pytest

from dataclasses import replace

from lazy_lab.engine.core_machine import (
    create_initial_core_state,
    run_batch,
)
from lazy_lab.engine.result_consumer import (
    InvalidResultObservationError,
    consume_whnf_result,
    select_result_mode,
    consume_materialized_result,
)
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.observation import (
    CanonicalInteger,
    CanonicalBoolean,
    OpaqueFunction,
)
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionStatus,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
    ExecutionPhase,
)
from lazy_lab.runtime.transitions import (
    BatchStopReason,
    RuleId,
    TransitionKind,
    TraceEntry,
)
from lazy_lab.engine.session_runner import run_session_batch

def make_config(policy=ResultPolicy.WHNF_ONLY):
    return ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBV,
        result_policy=policy,
        execution_step_limit=100,
        result_node_limit=100,
        trace_mode=TraceMode.FULL,
    )


@pytest.mark.parametrize(
    "source,expected",
    [
        ("main = 42", CanonicalInteger(42)),
        ("main = True", CanonicalBoolean(True)),
        ("main = 2 + 3", CanonicalInteger(5)),
    ],
)
def test_whnf_consumer_completes_primitive_result(
    source,
    expected,
):
    config = make_config()
    initial = create_initial_core_state(
        compile_source(source),
        config,
        session_id="whnf-consumer",
    )

    evaluated = run_batch(
        initial,
        config,
        max_steps=100,
    )

    assert evaluated.stop_reason is BatchStopReason.WHNF_PENDING

    previous = evaluated.state
    transition = consume_whnf_result(previous, config)

    completed = transition.next_state
    machine = completed.machine_state

    assert transition.rule_id is RuleId.RESULT_OBSERVE_WHNF
    assert transition.transition_kind is TransitionKind.RESULT_CONSUMER

    assert completed.canonical_result == expected
    assert machine.status is ExecutionStatus.COMPLETED

    assert machine.result_state.resolved_result_mode is (
        ResultPolicy.WHNF_ONLY
    )
    assert (
        machine.result_state.result_reference
        == previous.machine_state.control.reference
    )

    assert completed.transition_index == previous.transition_index + 1
    assert completed.state_id == previous.state_id + 1

    assert (
        machine.evaluator_transition_count
        == previous.machine_state.evaluator_transition_count
    )

    # Completion must not mutate the earlier state.
    assert previous.canonical_result is None
    assert previous.machine_state.status is ExecutionStatus.RUNNING


def test_whnf_consumer_returns_opaque_function():
    config = make_config()

    initial = create_initial_core_state(
        compile_source(r"main = \x -> x"),
        config,
        session_id="opaque-function-result",
    )

    evaluated = run_batch(
        initial,
        config,
        max_steps=100,
    )

    completed = consume_whnf_result(
        evaluated.state,
        config,
    ).next_state

    assert isinstance(completed.canonical_result, OpaqueFunction)
    assert completed.machine_state.status is ExecutionStatus.COMPLETED

    # The original closure remains in the heap.
    assert (
        completed.machine_state.heap.current_slots
        == evaluated.state.machine_state.heap.current_slots
    )


def test_whnf_consumer_rejects_invalid_boundaries():
    config = make_config()

    initial = create_initial_core_state(
        compile_source("main = 42"),
        config,
        session_id="invalid-result-boundary",
    )

    # Initialization is not a completed evaluation.
    with pytest.raises(InvalidResultObservationError):
        consume_whnf_result(initial, config)

    evaluated = run_batch(
        initial,
        config,
        max_steps=100,
    ).state

    completed = consume_whnf_result(
        evaluated,
        config,
    ).next_state

    # Result completion is not repeatable.
    with pytest.raises(InvalidResultObservationError):
        consume_whnf_result(completed, config)

    assert completed.canonical_result == CanonicalInteger(42)


def test_whnf_completion_produces_terminal_batch_status():
    config = make_config()

    initial = create_initial_core_state(
        compile_source("main = 42"),
        config,
        session_id="completed-batch",
    )

    evaluated = run_batch(
        initial,
        config,
        max_steps=100,
    )

    completed = consume_whnf_result(
        evaluated.state,
        config,
    ).next_state

    after_completion = run_batch(
        completed,
        config,
        max_steps=10,
    )

    assert after_completion.stop_reason is BatchStopReason.TERMINAL_STATUS
    assert after_completion.state is completed
    assert after_completion.trace == ()


def test_ask_at_whnf_waits_without_transitions():
    config = make_config(
        policy=ResultPolicy.ASK_AT_WHNF
    )

    initial = create_initial_core_state(
        compile_source("main = 42"),
        config,
        session_id="ask-waiting",
    )

    evaluated = run_batch(
        initial,
        config,
        max_steps=100,
    )

    assert evaluated.stop_reason is BatchStopReason.WHNF_PENDING

    waiting = evaluated.state

    repeated = run_batch(
        waiting,
        config,
        max_steps=100,
    )

    assert repeated.stop_reason is BatchStopReason.WHNF_PENDING
    assert repeated.state is waiting
    assert repeated.trace == ()

    assert waiting.canonical_result is None
    assert waiting.machine_state.status is ExecutionStatus.RUNNING
    assert waiting.machine_state.result_state.resolved_result_mode is None


def test_ask_at_whnf_can_select_whnf_only():
    config = make_config(
        policy=ResultPolicy.ASK_AT_WHNF
    )

    initial = create_initial_core_state(
        compile_source("main = 42"),
        config,
        session_id="ask-select-whnf",
    )

    waiting = run_batch(
        initial,
        config,
        max_steps=100,
    ).state

    selection = select_result_mode(
        waiting,
        config,
        ResultPolicy.WHNF_ONLY,
    )

    selected = selection.next_state

    assert selection.rule_id is RuleId.RESULT_SELECT_MODE
    assert selection.transition_kind is TransitionKind.RESULT_CONSUMER

    assert selected.machine_state.status is ExecutionStatus.RUNNING
    assert selected.canonical_result is None
    assert (
        selected.machine_state.result_state.resolved_result_mode
        is ResultPolicy.WHNF_ONLY
    )

    assert (
        selected.machine_state.evaluator_transition_count
        == waiting.machine_state.evaluator_transition_count
    )

    assert selected.transition_index == waiting.transition_index + 1

    completion = consume_whnf_result(
        selected,
        config,
    )

    completed = completion.next_state

    assert completed.canonical_result == CanonicalInteger(42)
    assert completed.machine_state.status is ExecutionStatus.COMPLETED
    assert completion.transition_kind is TransitionKind.RESULT_CONSUMER

    assert (
        completed.machine_state.evaluator_transition_count
        == waiting.machine_state.evaluator_transition_count
    )

    assert config.result_policy is ResultPolicy.ASK_AT_WHNF
    assert waiting.machine_state.result_state.resolved_result_mode is None


def test_ask_at_whnf_can_select_materialization():
    config = make_config(
        policy=ResultPolicy.ASK_AT_WHNF
    )

    initial = create_initial_core_state(
        compile_source("main = 42"),
        config,
        session_id="ask-materialize",
    )

    waiting = run_batch(
        initial,
        config,
        max_steps=100,
    ).state

    selected = select_result_mode(
        waiting,
        config,
        ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
    ).next_state

    assert (
        selected.machine_state.result_state.resolved_result_mode
        is ResultPolicy.MATERIALIZE_COMPLETE_VALUE
    )

    assert selected.machine_state.status is ExecutionStatus.RUNNING
    assert selected.canonical_result is None

    # The materialization consumer is implemented in B04.8.4.
    with pytest.raises(InvalidResultObservationError):
        consume_whnf_result(selected, config)

    assert selected.machine_state.control == waiting.machine_state.control
    assert selected.machine_state.stack.depth == 0


@pytest.mark.parametrize(
    "invalid_mode",
    [ResultPolicy.ASK_AT_WHNF, "WHNF_ONLY", "MATERIALIZE_COMPLETE_VALUE"],
)
def test_ask_at_whnf_rejects_invalid_selection(invalid_mode):
    config = make_config(
        policy=ResultPolicy.ASK_AT_WHNF
    )

    initial = create_initial_core_state(
        compile_source("main = 42"),
        config,
        session_id="ask-invalid",
    )

    with pytest.raises(InvalidResultObservationError):
        select_result_mode(
            initial,
            config,
            ResultPolicy.WHNF_ONLY,
        )

    waiting = run_batch(
        initial,
        config,
        max_steps=100,
    ).state

    with pytest.raises(InvalidResultObservationError):
        select_result_mode(
            waiting,
            config,
            invalid_mode,
        )

    selected = select_result_mode(
        waiting,
        config,
        ResultPolicy.WHNF_ONLY,
    ).next_state

    with pytest.raises(InvalidResultObservationError):
        select_result_mode(
            selected,
            config,
            ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
        )

    assert initial.transition_index == 0
    assert waiting.machine_state.result_state.resolved_result_mode is None


@pytest.mark.parametrize(
    "source,expected",
    [
        ("main = 42", CanonicalInteger(42)),
        ("main = True", CanonicalBoolean(True)),
        ("main = 2 + 3", CanonicalInteger(5)),
    ],
)
def test_materialize_atomic_result(source, expected):
    config = make_config(
        policy=ResultPolicy.MATERIALIZE_COMPLETE_VALUE
    )

    initial = create_initial_core_state(
        compile_source(source),
        config,
        session_id="materialize-atomic",
    )

    evaluated = run_batch(initial, config, max_steps=100)

    assert evaluated.stop_reason is BatchStopReason.WHNF_PENDING

    previous = evaluated.state

    transition = consume_materialized_result(
        previous,
        config,
    )

    completed = transition.next_state
    machine = completed.machine_state

    assert completed.canonical_result == expected
    assert machine.status is ExecutionStatus.COMPLETED

    assert (
        machine.phase
        is ExecutionPhase.RESULT_MATERIALIZATION
    )

    assert (
        machine.result_state.resolved_result_mode
        is ResultPolicy.MATERIALIZE_COMPLETE_VALUE
    )

    assert transition.rule_id is RuleId.RESULT_MATERIALIZE_ATOMIC
    assert transition.transition_kind is TransitionKind.RESULT_CONSUMER

    assert transition.phase_before is ExecutionPhase.EVALUATION
    assert transition.phase_after is ExecutionPhase.RESULT_MATERIALIZATION

    assert completed.transition_index == previous.transition_index + 1

    assert (
        machine.evaluator_transition_count
        == previous.machine_state.evaluator_transition_count
    )

    assert previous.canonical_result is None
    assert previous.machine_state.status is ExecutionStatus.RUNNING


def test_ask_at_whnf_can_complete_materialization():
    config = make_config(
        policy=ResultPolicy.ASK_AT_WHNF
    )

    initial = create_initial_core_state(
        compile_source("main = 10 * 4"),
        config,
        session_id="ask-complete-materialization",
    )

    waiting = run_batch(
        initial,
        config,
        max_steps=100,
    ).state

    selected = select_result_mode(
        waiting,
        config,
        ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
    ).next_state

    completed = consume_materialized_result(
        selected,
        config,
    ).next_state

    assert completed.canonical_result == CanonicalInteger(40)
    assert completed.machine_state.status is ExecutionStatus.COMPLETED

    assert (
        completed.machine_state.result_state.resolved_result_mode
        is ResultPolicy.MATERIALIZE_COMPLETE_VALUE
    )

    # One administrative transition for selection and
    # one for atomic materialization.
    assert completed.transition_index == waiting.transition_index + 2

    assert (
        completed.machine_state.evaluator_transition_count
        == waiting.machine_state.evaluator_transition_count
    )

    assert config.result_policy is ResultPolicy.ASK_AT_WHNF
    assert waiting.canonical_result is None


@pytest.mark.parametrize(
    "source",
    [
        r"main = \x -> x",
        "main = seq",
        "main = seq 10",
    ],
)
def test_materialize_function_as_opaque(source):
    config = make_config(
        policy=ResultPolicy.MATERIALIZE_COMPLETE_VALUE
    )

    initial = create_initial_core_state(
        compile_source(source),
        config,
        session_id="materialize-function",
    )

    evaluated = run_batch(
        initial,
        config,
        max_steps=100,
    )

    completed = consume_materialized_result(
        evaluated.state,
        config,
    ).next_state

    assert isinstance(completed.canonical_result, OpaqueFunction)
    assert completed.machine_state.status is ExecutionStatus.COMPLETED

    assert (
        completed.machine_state.heap.current_slots
        == evaluated.state.machine_state.heap.current_slots
    )


def test_materialization_rejects_wrong_policy():
    config = make_config(policy=ResultPolicy.WHNF_ONLY)

    initial = create_initial_core_state(
        compile_source("main = 42"),
        config,
        session_id="wrong-materialization-policy",
    )

    evaluated = run_batch(
        initial,
        config,
        max_steps=100,
    ).state

    with pytest.raises(InvalidResultObservationError):
        consume_materialized_result(evaluated, config)

    assert evaluated.canonical_result is None
    assert evaluated.machine_state.status is ExecutionStatus.RUNNING


def test_materialization_cannot_complete_twice():
    config = make_config(
        policy=ResultPolicy.MATERIALIZE_COMPLETE_VALUE
    )

    initial = create_initial_core_state(
        compile_source("main = 42"),
        config,
        session_id="duplicate-materialization",
    )

    evaluated = run_batch(
        initial,
        config,
        max_steps=100,
    ).state

    completed = consume_materialized_result(
        evaluated,
        config,
    ).next_state

    with pytest.raises(InvalidResultObservationError):
        consume_materialized_result(completed, config)

    assert completed.canonical_result == CanonicalInteger(42)
    assert evaluated.canonical_result is None


def test_session_batch_matches_single_step_execution():
    config = replace(
        make_config(policy=ResultPolicy.WHNF_ONLY),
        execution_step_limit=300,
    )

    initial = create_initial_core_state(
        compile_source("main = seq (2 + 3) (10 * 4)"),
        config,
        session_id="session-batch-equivalence",
    )

    # Complete execution.
    full = run_session_batch(
        initial,
        config,
        max_steps=300,
    )

    # Same execution using one transition per batch.
    current = initial
    collected_trace = []

    for _ in range(300):
        batch = run_session_batch(
            current,
            config,
            max_steps=1,
        )

        current = batch.state
        collected_trace.extend(batch.trace)

        if batch.stop_reason is BatchStopReason.TERMINAL_STATUS:
            break

        assert batch.stop_reason is BatchStopReason.BATCH_LIMIT
    else:
        pytest.fail("Chunked session did not complete")

    assert current.canonical_result == CanonicalInteger(40)
    assert current.canonical_result == full.state.canonical_result

    assert current.machine_state.status is ExecutionStatus.COMPLETED
    assert tuple(collected_trace) == full.trace

    assert current.transition_index == full.state.transition_index
    assert (
        current.machine_state.evaluator_transition_count
        == full.state.machine_state.evaluator_transition_count
    )

    assert (
        current.machine_state.heap.current_slots
        == full.state.machine_state.heap.current_slots
    )

    assert initial.transition_index == 0


def test_session_batch_can_stop_before_result_consumption():
    config = make_config(
        policy=ResultPolicy.WHNF_ONLY
    )

    initial = create_initial_core_state(
        compile_source("main = 42"),
        config,
        session_id="batch-boundary",
    )

    evaluated = run_batch(
        initial,
        config,
        max_steps=100,
    )

    assert evaluated.stop_reason is BatchStopReason.WHNF_PENDING

    evaluator_steps = (
        evaluated.state.transition_index - initial.transition_index
    )

    # Consume exactly the evaluator's number of transitions.
    partial = run_session_batch(
        initial,
        config,
        max_steps=evaluator_steps,
    )

    assert partial.stop_reason is BatchStopReason.BATCH_LIMIT
    assert partial.state.canonical_result is None
    assert partial.state.machine_state.status is ExecutionStatus.RUNNING

    # The next batch uses one administrative transition.
    completed = run_session_batch(
        partial.state,
        config,
        max_steps=1,
    )

    assert completed.stop_reason is BatchStopReason.TERMINAL_STATUS
    assert completed.state.canonical_result == CanonicalInteger(42)

    assert (
        completed.state.machine_state.evaluator_transition_count
        == partial.state.machine_state.evaluator_transition_count
    )


def test_session_batch_waits_for_result_selection():
    config = make_config(
        policy=ResultPolicy.ASK_AT_WHNF
    )

    initial = create_initial_core_state(
        compile_source("main = 42"),
        config,
        session_id="session-ask",
    )

    waiting = run_session_batch(
        initial,
        config,
        max_steps=100,
    )

    assert waiting.stop_reason is BatchStopReason.WHNF_PENDING

    repeated = run_session_batch(
        waiting.state,
        config,
        max_steps=100,
    )

    assert repeated.state is waiting.state
    assert repeated.trace == ()
    assert repeated.stop_reason is BatchStopReason.WHNF_PENDING

    selection = select_result_mode(
        waiting.state,
        config,
        ResultPolicy.WHNF_ONLY,
    )

    completed = run_session_batch(
        selection.next_state,
        config,
        max_steps=1,
    )

    assert completed.stop_reason is BatchStopReason.TERMINAL_STATUS
    assert completed.state.canonical_result == CanonicalInteger(42)

    # Mode selection and completion are administrative.
    assert (
        completed.state.machine_state.evaluator_transition_count
        == waiting.state.machine_state.evaluator_transition_count
    )

    assert (
        completed.state.transition_index
        == waiting.state.transition_index + 2
    )


def test_result_consumer_does_not_require_evaluator_budget():
    config = make_config(
        policy=ResultPolicy.WHNF_ONLY
    )

    initial = create_initial_core_state(
        compile_source("main = 42"),
        config,
        session_id="consumer-budget",
    )

    evaluated = run_batch(
        initial,
        config,
        max_steps=100,
    ).state

    used_evaluator_steps = (
        evaluated.machine_state.evaluator_transition_count
    )

    limited_config = replace(
        config,
        execution_step_limit=used_evaluator_steps,
    )

    completed = run_session_batch(
        evaluated,
        limited_config,
        max_steps=1,
    )

    assert completed.stop_reason is BatchStopReason.TERMINAL_STATUS

    assert (
        completed.state.machine_state.evaluator_transition_count
        == used_evaluator_steps
    )

    assert (
        completed.state.transition_index
        == evaluated.transition_index + 1
    )


def test_atomic_materialization_respects_minimum_node_limit():
    config = replace(
        make_config(
            policy=ResultPolicy.MATERIALIZE_COMPLETE_VALUE
        ),
        result_node_limit=1,
    )

    initial = create_initial_core_state(
        compile_source("main = 42"),
        config,
        session_id="materialize-one-node",
    )

    result = run_session_batch(
        initial,
        config,
        max_steps=100,
    )

    assert result.stop_reason is BatchStopReason.TERMINAL_STATUS
    assert result.state.canonical_result == CanonicalInteger(42)
    assert result.state.machine_state.status is ExecutionStatus.COMPLETED


@pytest.mark.parametrize(
    "policy",
    [ResultPolicy.WHNF_ONLY, ResultPolicy.MATERIALIZE_COMPLETE_VALUE],
)
@pytest.mark.parametrize(
    "source,expected",
    [
        ("main = seq 0 (2 + 3)", CanonicalInteger(5)),
        ("main = seq 0 False", CanonicalBoolean(False)),
        ("main = seq 10", OpaqueFunction()),
    ],
)
def test_session_trace_modes_consume_at_exact_evaluator_limit(
    policy, source, expected,
):
    config = replace(make_config(policy=policy), result_node_limit=1)
    initial = create_initial_core_state(
        compile_source(source), config, session_id="session-trace-limits",
    )
    evaluated = run_batch(initial, config, max_steps=100)
    assert evaluated.stop_reason is BatchStopReason.WHNF_PENDING
    evaluator_steps = evaluated.state.machine_state.evaluator_transition_count

    results = {}
    for mode in TraceMode:
        limited_config = replace(
            config, trace_mode=mode, execution_step_limit=evaluator_steps,
        )
        paused = run_session_batch(
            initial, limited_config, max_steps=evaluator_steps,
        )
        assert paused.stop_reason is BatchStopReason.BATCH_LIMIT
        assert paused.state.transition_index == evaluator_steps
        assert paused.state.canonical_result is None
        before = paused.state.snapshot()

        completed = run_session_batch(paused.state, limited_config, max_steps=1)
        full = run_session_batch(
            initial, limited_config, max_steps=evaluator_steps + 1,
        )
        assert paused.trace + completed.trace == full.trace
        for result in (completed, full):
            machine = result.state.machine_state
            assert result.stop_reason is BatchStopReason.TERMINAL_STATUS
            assert machine.status is ExecutionStatus.COMPLETED
            if isinstance(expected, OpaqueFunction):
                assert isinstance(result.state.canonical_result, OpaqueFunction)
            else:
                assert result.state.canonical_result == expected
            assert result.state.state_id == evaluator_steps + 1
            assert result.state.transition_index == evaluator_steps + 1
            assert machine.evaluator_transition_count == evaluator_steps
            assert machine.result_state.resolved_result_mode is policy
            assert machine.stack.depth == 0
            assert machine.heap.current_slots == before.machine_state.heap.current_slots
            assert machine.heap.next_object_id == before.machine_state.heap.next_object_id

        assert completed.state.machine_state.heap is not paused.state.machine_state.heap
        assert dict(paused.state.machine_state.heap.cells) == dict(before.machine_state.heap.cells)
        assert paused.state.machine_state.stack.frames == before.machine_state.stack.frames
        assert paused.state.machine_state.status is ExecutionStatus.RUNNING
        assert paused.state.machine_state.result_state.resolved_result_mode is None
        assert paused.state.canonical_result is None
        results[mode] = full

    assert results[TraceMode.FULL].trace == results[TraceMode.EVENTS].trace
    assert results[TraceMode.METRICS_ONLY].trace == ()
    assert results[TraceMode.FULL].trace[-1].transition_kind is TransitionKind.RESULT_CONSUMER
    assert initial.transition_index == 0
    assert initial.machine_state.heap.current_slots == 0


@pytest.mark.parametrize(
    "selected_mode",
    [ResultPolicy.WHNF_ONLY, ResultPolicy.MATERIALIZE_COMPLETE_VALUE],
)
def test_ask_single_step_batches_preserve_snapshots_and_terminal_state(selected_mode):
    config = make_config(policy=ResultPolicy.ASK_AT_WHNF)
    initial = create_initial_core_state(
        compile_source("main = seq (2 + 3) True"),
        config, session_id="ask-single-step",
    )
    full_waiting = run_session_batch(initial, config, max_steps=100)
    full_selection = select_result_mode(full_waiting.state, config, selected_mode)
    full_completed = run_session_batch(full_selection.next_state, config, max_steps=100)

    current = initial
    trace = []
    for _ in range(config.execution_step_limit):
        batch = run_session_batch(current, config, max_steps=1)
        assert batch.state.transition_index - current.transition_index <= 1
        current = batch.state
        trace.extend(batch.trace)
        if batch.stop_reason is BatchStopReason.WHNF_PENDING:
            break
        assert batch.stop_reason is BatchStopReason.BATCH_LIMIT
    else:
        pytest.fail("Single-step ASK session did not reach WHNF")

    assert full_waiting.stop_reason is BatchStopReason.WHNF_PENDING
    assert tuple(trace) == full_waiting.trace
    waiting = current
    waiting_snapshot = waiting.snapshot()
    repeated = run_session_batch(waiting, config, max_steps=1)
    assert repeated.stop_reason is BatchStopReason.WHNF_PENDING
    assert repeated.state is waiting
    assert repeated.trace == ()

    selection = select_result_mode(waiting, config, selected_mode)
    selected = selection.next_state
    selected_snapshot = selected.snapshot()
    trace.append(TraceEntry.from_transition(selection))
    completed = run_session_batch(selected, config, max_steps=1)
    trace.extend(completed.trace)
    assert completed.stop_reason is BatchStopReason.TERMINAL_STATUS
    assert completed.state.canonical_result == CanonicalBoolean(True)
    assert completed.state.canonical_result == full_completed.state.canonical_result
    assert tuple(trace) == (
        full_waiting.trace
        + (TraceEntry.from_transition(full_selection),)
        + full_completed.trace
    )
    evaluator_steps = waiting.machine_state.evaluator_transition_count
    assert selected.state_id == waiting.state_id + 1
    assert selected.transition_index == waiting.transition_index + 1
    assert selected.machine_state.evaluator_transition_count == evaluator_steps
    assert completed.state.state_id == waiting.state_id + 2
    assert completed.state.transition_index == evaluator_steps + 2
    assert completed.state.machine_state.evaluator_transition_count == evaluator_steps
    assert config.result_policy is ResultPolicy.ASK_AT_WHNF

    terminal = run_session_batch(completed.state, config, max_steps=1)
    assert terminal.stop_reason is BatchStopReason.TERMINAL_STATUS
    assert terminal.state is completed.state
    assert terminal.trace == ()
    for operation in (consume_whnf_result, consume_materialized_result):
        with pytest.raises(InvalidResultObservationError):
            operation(completed.state, config)
    with pytest.raises(InvalidResultObservationError):
        select_result_mode(completed.state, config, selected_mode)

    for previous, snapshot in (
        (waiting, waiting_snapshot), (selected, selected_snapshot),
    ):
        assert previous.canonical_result is None
        assert previous.machine_state.status is ExecutionStatus.RUNNING
        assert previous.machine_state.control is snapshot.machine_state.control
        assert previous.machine_state.result_state == snapshot.machine_state.result_state
        assert dict(previous.machine_state.heap.cells) == dict(snapshot.machine_state.heap.cells)
        assert previous.machine_state.stack.frames == snapshot.machine_state.stack.frames
    assert waiting.machine_state.result_state.resolved_result_mode is None
    assert selected.machine_state.result_state.resolved_result_mode is selected_mode
