
import pytest

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
)


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


def test_ask_at_whnf_rejects_invalid_selection():
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
            ResultPolicy.ASK_AT_WHNF,
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
