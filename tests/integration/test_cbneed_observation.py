
from dataclasses import replace

import pytest

from lazy_lab.engine.core_machine import create_initial_core_state, run_batch, step
from lazy_lab.engine.session_runner import run_session_batch
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.control import Force
from lazy_lab.runtime.observation import (
    CanonicalBoolean,
    CanonicalInteger,
    OpaqueFunction,
    UnresolvedObservationError,
    observe_whnf,
)
from lazy_lab.runtime.state import ExecutionPhase, ExecutionStatus, ResultPolicy
from lazy_lab.runtime.thunks import EvaluatingThunk, PendingThunk
from lazy_lab.runtime.transitions import BatchStopReason, RuleId, TransitionKind
from tests.integration.test_cbneed_application import make_cbneed_config
from tests.integration.test_cbneed_seq import advance_to_seq_saturation


def test_cbneed_observation_rejects_pending_thunk():
    program = compile_source(
        "main = seq 10 (20 + 22)"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-observe-pending",
    )

    saturated, _ = advance_to_seq_saturation(
        initial, config
    )

    machine = saturated.machine_state
    second_ref = machine.control.reference

    assert isinstance(
        machine.heap.get(second_ref).value,
        PendingThunk,
    )

    before_cells = dict(machine.heap.cells)
    before_count = machine.evaluator_transition_count

    with pytest.raises(UnresolvedObservationError):
        observe_whnf(machine.heap, second_ref)

    assert dict(machine.heap.cells) == before_cells
    assert machine.evaluator_transition_count == before_count
    assert isinstance(
        machine.heap.get(second_ref).value,
        PendingThunk,
    )

    current = saturated
    for _ in range(150):
        transition = step(current, config)

        if (
            transition.rule_id is RuleId.CORE_FORCE_THUNK_ENTER
            and current.machine_state.control == Force(second_ref)
        ):
            checkpoint = transition.next_state
            break

        current = transition.next_state
    else:
        pytest.fail("Second argument thunk entry was not reached")

    machine = checkpoint.machine_state
    assert isinstance(
        machine.heap.get(second_ref).value,
        EvaluatingThunk,
    )

    before_cells = dict(machine.heap.cells)
    before_count = machine.evaluator_transition_count

    with pytest.raises(UnresolvedObservationError):
        observe_whnf(machine.heap, second_ref)

    assert dict(machine.heap.cells) == before_cells
    assert machine.evaluator_transition_count == before_count
    assert isinstance(
        machine.heap.get(second_ref).value,
        EvaluatingThunk,
    )


@pytest.mark.parametrize(
    "source, expected",
    [
        (
            "main = seq (10 + 1) 42",
            CanonicalInteger(42),
        ),
        (
            "main = seq True False",
            CanonicalBoolean(False),
        ),
        (
            r"main = seq 10 (\x -> x)",
            OpaqueFunction,
        ),
    ],
)
@pytest.mark.parametrize(
    "policy, expected_rule",
    [
        (
            ResultPolicy.WHNF_ONLY,
            RuleId.RESULT_OBSERVE_WHNF,
        ),
        (
            ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
            RuleId.RESULT_MATERIALIZE_ATOMIC,
        ),
    ],
)
def test_cbneed_fixed_result_policies(
    source, expected, policy, expected_rule
):
    config = replace(
        make_cbneed_config(),
        result_policy=policy,
        execution_step_limit=300,
    )

    initial = create_initial_core_state(
        compile_source(source),
        config,
        session_id="cbneed-result-policies",
    )

    evaluated = run_batch(
        initial, config, max_steps=300
    )

    assert evaluated.stop_reason is BatchStopReason.WHNF_PENDING

    before = evaluated.state
    before_count = (
        before.machine_state.evaluator_transition_count
    )

    assert before.canonical_result is None
    assert before.machine_state.status is ExecutionStatus.RUNNING
    assert before.machine_state.phase is ExecutionPhase.EVALUATION

    before_cells = dict(before.machine_state.heap.cells)
    before_slots = before.machine_state.heap.current_slots
    before_next_id = before.machine_state.heap.next_object_id

    # The result consumer completes the already-WHNF value.
    consumed = run_session_batch(
        before, config, max_steps=1
    )

    assert consumed.stop_reason is BatchStopReason.TERMINAL_STATUS
    assert len(consumed.trace) == 1
    assert consumed.trace[0].rule_id is expected_rule
    assert (
        consumed.trace[0].transition_kind
        is TransitionKind.RESULT_CONSUMER
    )

    final = consumed.state

    if expected is OpaqueFunction:
        assert isinstance(final.canonical_result, OpaqueFunction)
        # Returning and observing a lambda must never enter its body.
        assert all(
            entry.rule_id is not RuleId.CORE_CBNEED_ENTER_BODY
            for entry in (*evaluated.trace, *consumed.trace)
        )
    else:
        assert final.canonical_result == expected

    assert dict(final.machine_state.heap.cells) == before_cells
    assert final.machine_state.heap.current_slots == before_slots
    assert final.machine_state.heap.next_object_id == before_next_id
    assert final.machine_state.control == before.machine_state.control
    assert final.machine_state.stack.frames == before.machine_state.stack.frames
    assert final.machine_state.status is ExecutionStatus.COMPLETED
    assert (
        final.machine_state.evaluator_transition_count
        == before_count
    )
    assert final.transition_index == before.transition_index + 1

    expected_phase = (
        ExecutionPhase.EVALUATION
        if policy is ResultPolicy.WHNF_ONLY
        else ExecutionPhase.RESULT_MATERIALIZATION
    )

    assert final.machine_state.phase is expected_phase
    assert final.machine_state.result_state.resolved_result_mode is policy

    # The observation boundary remains independently inspectable.
    assert before.canonical_result is None
    assert before.machine_state.status is ExecutionStatus.RUNNING
