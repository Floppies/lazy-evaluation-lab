
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

    if config.result_policy is not ResultPolicy.WHNF_ONLY:
        raise InvalidResultObservationError(
            "WHNF_ONLY result policy is required"
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

    if (
        state.canonical_result is not None
        or machine.result_state.resolved_result_mode is not None
    ):
        raise InvalidResultObservationError(
            "Result has already been observed"
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
