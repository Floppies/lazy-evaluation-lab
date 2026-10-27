
"""Result-consumer transitions for canonical observation."""

from __future__ import annotations

from dataclasses import replace

from lazy_lab.runtime.control import Return
from lazy_lab.runtime.observation import observe_whnf
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionPhase,
    ExecutionState,
    ExecutionStatus,
    MachineKind,
    ResultPolicy,
)
from lazy_lab.runtime.transitions import (
    RuleId,
    TransitionKind,
    TransitionResult,
)


class InvalidResultObservationError(ValueError):
    """The machine is not ready for the requested observation."""

def consume_whnf_result(
    state: ExecutionState,
    config: ExecutionConfig,
) -> TransitionResult:
    """Complete an already-WHNF Core result without evaluator work."""
    machine = state.machine_state

    if (
        machine.machine_kind is not config.machine_kind
        or machine.strategy is not config.strategy
    ):
        raise InvalidResultObservationError(
            "Execution configuration does not match the machine"
        )

    if machine.machine_kind is not MachineKind.CORE:
        raise InvalidResultObservationError(
            "Only Core result observation is supported"
        )

    if (
        machine.status is not ExecutionStatus.RUNNING
        or machine.phase is not ExecutionPhase.EVALUATION
    ):
        raise InvalidResultObservationError(
            "Result observation requires a running evaluation"
        )

    if (
        not isinstance(machine.control, Return)
        or machine.stack.depth != 0
    ):
        raise InvalidResultObservationError(
            "Result observation requires a root Return"
        )
    
    if state.canonical_result is not None:
        raise InvalidResultObservationError(
            "Result has already been observed"
        )

    result_state = machine.result_state

    if config.result_policy is ResultPolicy.WHNF_ONLY:
        # Fixed policy: no previous mode selection is expected.
        if (
            result_state.resolved_result_mode is not None
            or result_state.result_reference is not None
        ):
            raise InvalidResultObservationError(
                "Unexpected previous result selection"
            )

    elif config.result_policy is ResultPolicy.ASK_AT_WHNF:
        # Interactive policy: WHNF_ONLY must have been selected.
        if (
            result_state.resolved_result_mode
            is not ResultPolicy.WHNF_ONLY
            or result_state.result_reference
            != machine.control.reference
        ):
            raise InvalidResultObservationError(
                "WHNF_ONLY has not been selected"
            )

    else:
        raise InvalidResultObservationError(
            "WHNF_ONLY result mode is required"
        )

    reference = machine.control.reference

    # Passive conversion: this cannot execute or force a value.
    # Unresolved references are rejected by observe_whnf.
    canonical = observe_whnf(machine.heap, reference)

    # Preserve the previous execution snapshot.
    snapshot = state.snapshot()

    next_result_state = replace(
        snapshot.machine_state.result_state,
        result_reference=reference,
        resolved_result_mode=ResultPolicy.WHNF_ONLY,
    )

    next_machine = replace(
        snapshot.machine_state,
        status=ExecutionStatus.COMPLETED,
        result_state=next_result_state,
    )

    next_state = replace(
        snapshot,
        state_id=state.state_id + 1,
        transition_index=state.transition_index + 1,
        machine_state=next_machine,
        canonical_result=canonical,
    )

    return TransitionResult(
        previous_state_id=state.state_id,
        next_state=next_state,
        rule_id=RuleId.RESULT_OBSERVE_WHNF,
        transition_kind=TransitionKind.RESULT_CONSUMER,
        phase_before=machine.phase,
        phase_after=next_machine.phase,
    )

def select_result_mode(
    state: ExecutionState,
    config: ExecutionConfig,
    selected_mode: ResultPolicy,
) -> TransitionResult:
    """Record an explicit result-observation choice."""

    machine = state.machine_state

    if config.result_policy is not ResultPolicy.ASK_AT_WHNF:
        raise InvalidResultObservationError(
            "ASK_AT_WHNF policy is required"
        )

    if (
        selected_mode
        not in (
            ResultPolicy.WHNF_ONLY,
            ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
        )
    ):
        raise InvalidResultObservationError(
            "Invalid resolved result mode"
        )

    if (
        machine.machine_kind is not config.machine_kind
        or machine.strategy is not config.strategy
        or machine.machine_kind is not MachineKind.CORE
    ):
        raise InvalidResultObservationError(
            "Invalid result observation configuration"
        )

    if (
        machine.status is not ExecutionStatus.RUNNING
        or machine.phase is not ExecutionPhase.EVALUATION
        or not isinstance(machine.control, Return)
        or machine.stack.depth != 0
    ):
        raise InvalidResultObservationError(
            "Result is not ready for observation"
        )

    if (
        state.canonical_result is not None
        or machine.result_state.result_reference is not None
        or machine.result_state.resolved_result_mode is not None
    ):
        raise InvalidResultObservationError(
            "Result mode has already been selected"
        )

    reference = machine.control.reference

    # Validate that the result has reached observable WHNF.
    # This conversion is passive and its output is not stored yet.
    observe_whnf(machine.heap, reference)

    snapshot = state.snapshot()

    result_state = replace(
        snapshot.machine_state.result_state,
        result_reference=reference,
        resolved_result_mode=selected_mode,
    )

    next_machine = replace(
        snapshot.machine_state,
        result_state=result_state,
    )

    next_state = replace(
        snapshot,
        state_id=state.state_id + 1,
        transition_index=state.transition_index + 1,
        machine_state=next_machine,
    )

    return TransitionResult(
        previous_state_id=state.state_id,
        next_state=next_state,
        rule_id=RuleId.RESULT_SELECT_MODE,
        transition_kind=TransitionKind.RESULT_CONSUMER,
        phase_before=machine.phase,
        phase_after=next_machine.phase,
    )


def consume_materialized_result(
    state: ExecutionState,
    config: ExecutionConfig,
) -> TransitionResult:
    """Materialize an already-WHNF atomic or opaque result."""

    machine = state.machine_state

    if (
        machine.machine_kind is not config.machine_kind
        or machine.strategy is not config.strategy
        or machine.machine_kind is not MachineKind.CORE
    ):
        raise InvalidResultObservationError(
            "Invalid result observation configuration"
        )

    if (
        machine.status is not ExecutionStatus.RUNNING
        or machine.phase is not ExecutionPhase.EVALUATION
    ):
        raise InvalidResultObservationError(
            "Materialization requires a running evaluation"
        )

    if (
        not isinstance(machine.control, Return)
        or machine.stack.depth != 0
    ):
        raise InvalidResultObservationError(
            "Materialization requires a root Return"
        )

    if state.canonical_result is not None:
        raise InvalidResultObservationError(
            "Result has already been materialized"
        )

    reference = machine.control.reference
    result_state = machine.result_state

    if (
        config.result_policy
        is ResultPolicy.MATERIALIZE_COMPLETE_VALUE
    ):
        # Fixed policy: no previous selection is expected.
        if (
            result_state.resolved_result_mode is not None
            or result_state.result_reference is not None
        ):
            raise InvalidResultObservationError(
                "Unexpected previous result selection"
            )

    elif config.result_policy is ResultPolicy.ASK_AT_WHNF:
        # Interactive policy: materialization was selected.
        if (
            result_state.resolved_result_mode
            is not ResultPolicy.MATERIALIZE_COMPLETE_VALUE
            or result_state.result_reference != reference
        ):
            raise InvalidResultObservationError(
                "Materialization has not been selected"
            )

    else:
        raise InvalidResultObservationError(
            "MATERIALIZE_COMPLETE_VALUE policy is required"
        )

    # The current runtime supports only atomic or opaque
    # WHNF results. No recursive traversal is necessary.
    canonical = observe_whnf(machine.heap, reference)

    # No additional evaluator work is performed.
    snapshot = state.snapshot()

    next_result_state = replace(
        snapshot.machine_state.result_state,
        result_reference=reference,
        resolved_result_mode=ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
    )

    next_machine = replace(
        snapshot.machine_state,
        status=ExecutionStatus.COMPLETED,
        phase=ExecutionPhase.RESULT_MATERIALIZATION,
        result_state=next_result_state,
    )

    next_state = replace(
        snapshot,
        state_id=state.state_id + 1,
        transition_index=state.transition_index + 1,
        machine_state=next_machine,
        canonical_result=canonical,
    )

    return TransitionResult(
        previous_state_id=state.state_id,
        next_state=next_state,
        rule_id=RuleId.RESULT_MATERIALIZE_ATOMIC,
        transition_kind=TransitionKind.RESULT_CONSUMER,
        phase_before=machine.phase,
        phase_after=next_machine.phase,
    )
