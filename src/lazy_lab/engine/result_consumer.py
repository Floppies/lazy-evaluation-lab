
"""Result-consumer transitions for canonical observation."""

from __future__ import annotations

from dataclasses import replace

from lazy_lab.runtime.constructors import ConstructorValue
from lazy_lab.runtime.control import Force, Return
from lazy_lab.runtime.materialization import (
    MaterializationState,
    advance_materialization,
    build_partial_value,
    start_materialization,
)
from lazy_lab.runtime.observation import observe_whnf
from lazy_lab.runtime.references import HeapReference
from lazy_lab.runtime.stack import MaterializationDemandFrame
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

from lazy_lab.metrics.recording import StackEffectRecorder


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
        not isinstance(selected_mode, ResultPolicy)
        or selected_mode
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

    if (
        isinstance(reference, HeapReference)
        and isinstance(
            machine.heap.get(reference).value,
            ConstructorValue,
        )
    ):
        raise InvalidResultObservationError(
            "Constructor results require the dedicated "
            "constructor materialization protocol"
        )

    # This helper handles atomic or opaque WHNF results only.
    # Recursive constructor traversal uses the separate
    # constructor materialization protocol.
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

def start_constructor_materialization(
    state: ExecutionState,
    config: ExecutionConfig,
) -> TransitionResult:
    """Enter constructor materialization without visiting the root."""
    machine = state.machine_state
    result_state = machine.result_state

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
            "Constructor materialization requires an evaluation root Return"
        )

    if (
        state.canonical_result is not None
        or result_state.materialization is not None
    ):
        raise InvalidResultObservationError(
            "Constructor materialization has already started"
        )

    reference = machine.control.reference

    if config.result_policy is ResultPolicy.MATERIALIZE_COMPLETE_VALUE:
        if (
            result_state.resolved_result_mode is not None
            or result_state.result_reference is not None
        ):
            raise InvalidResultObservationError(
                "Unexpected previous result selection"
            )
    elif config.result_policy is ResultPolicy.ASK_AT_WHNF:
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

    if (
        not isinstance(reference, HeapReference)
        or not isinstance(machine.heap.get(reference).value, ConstructorValue)
    ):
        raise InvalidResultObservationError(
            "Constructor materialization requires a constructor in WHNF"
        )

    snapshot = state.snapshot()
    progress = start_materialization(reference)
    next_result_state = replace(
        snapshot.machine_state.result_state,
        result_reference=reference,
        resolved_result_mode=ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
        materialization=progress,
    )
    next_machine = replace(
        snapshot.machine_state,
        phase=ExecutionPhase.RESULT_MATERIALIZATION,
        result_state=next_result_state,
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
        rule_id=RuleId.RESULT_MATERIALIZE_START,
        transition_kind=TransitionKind.RESULT_CONSUMER,
        phase_before=machine.phase,
        phase_after=next_machine.phase,
    )


def _constructor_materialization_progress(
    state: ExecutionState,
    config: ExecutionConfig,
    *,
    require_root_return: bool = True,
) -> MaterializationState:
    """Validate an active consumer, optionally during field evaluation."""
    machine = state.machine_state
    result_state = machine.result_state
    progress = result_state.materialization

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
        or machine.phase is not ExecutionPhase.RESULT_MATERIALIZATION
        or state.canonical_result is not None
        or progress is None
    ):
        raise InvalidResultObservationError(
            "No active constructor materialization"
        )

    if (
        config.result_policy not in (
            ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
            ResultPolicy.ASK_AT_WHNF,
        )
        or result_state.resolved_result_mode
        is not ResultPolicy.MATERIALIZE_COMPLETE_VALUE
        or result_state.result_reference != progress.root_reference
    ):
        raise InvalidResultObservationError(
            "Invalid constructor materialization selection"
        )

    if require_root_return and (
        not isinstance(machine.control, Return)
        or machine.control.reference != progress.root_reference
        or machine.stack.depth != 0
    ):
        raise InvalidResultObservationError(
            "Constructor materialization requires a root Return"
        )

    return progress


def advance_constructor_materialization(
    state: ExecutionState,
    config: ExecutionConfig,
) -> TransitionResult:
    """Advance one DFS operation without executing evaluator work."""
    machine = state.machine_state
    progress = _constructor_materialization_progress(state, config)
    if (
        progress.completed_value is not None
        or progress.limit_reached
        or progress.awaiting_whnf
    ):
        raise InvalidResultObservationError(
            "Materialization is not ready for a DFS advance"
        )

    next_progress = advance_materialization(
        machine.heap,
        progress,
        node_limit=config.result_node_limit,
    )
    snapshot = state.snapshot()
    next_machine = replace(
        snapshot.machine_state,
        result_state=replace(
            snapshot.machine_state.result_state,
            materialization=next_progress,
        ),
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
        rule_id=RuleId.RESULT_MATERIALIZE_ADVANCE,
        transition_kind=TransitionKind.RESULT_CONSUMER,
        phase_before=machine.phase,
        phase_after=next_machine.phase,
    )


def complete_constructor_materialization(
    state: ExecutionState,
    config: ExecutionConfig,
) -> TransitionResult:
    """Publish the completed canonical tree without traversing it again."""
    machine = state.machine_state
    progress = _constructor_materialization_progress(state, config)
    if (
        progress.completed_value is None
        or progress.limit_reached
        or progress.awaiting_whnf
    ):
        raise InvalidResultObservationError(
            "Constructor materialization is not complete"
        )

    snapshot = state.snapshot()
    next_machine = replace(
        snapshot.machine_state,
        status=ExecutionStatus.COMPLETED,
    )
    next_state = replace(
        snapshot,
        state_id=state.state_id + 1,
        transition_index=state.transition_index + 1,
        machine_state=next_machine,
        canonical_result=progress.completed_value,
    )
    return TransitionResult(
        previous_state_id=state.state_id,
        next_state=next_state,
        rule_id=RuleId.RESULT_MATERIALIZE_COMPLETE,
        transition_kind=TransitionKind.RESULT_CONSUMER,
        phase_before=machine.phase,
        phase_after=next_machine.phase,
    )


def finish_limited_materialization(
    state: ExecutionState,
    config: ExecutionConfig,
) -> TransitionResult:
    """Publish a partial tree at a result or evaluator limit."""
    machine = state.machine_state
    progress = _constructor_materialization_progress(
        state, config, require_root_return=False,
    )
    if progress.completed_value is not None:
        raise InvalidResultObservationError(
            "Constructor materialization is already complete"
        )

    if progress.limit_reached:
        if progress.partial_value is None:
            raise InvalidResultObservationError(
                "Limited materialization has no partial value"
            )
        canonical = progress.partial_value
        status = ExecutionStatus.RESULT_LIMIT_REACHED
        rule_id = RuleId.RESULT_MATERIALIZE_RESULT_LIMIT
    elif (
        progress.awaiting_whnf
        and machine.evaluator_transition_count >= config.execution_step_limit
    ):
        canonical = build_partial_value(progress)
        status = ExecutionStatus.STEP_LIMIT_REACHED
        rule_id = RuleId.RESULT_MATERIALIZE_EXECUTION_LIMIT
    else:
        raise InvalidResultObservationError(
            "No materialization limit requires termination"
        )

    snapshot = state.snapshot()
    next_machine = replace(snapshot.machine_state, status=status)
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
        rule_id=rule_id,
        transition_kind=TransitionKind.RESULT_CONSUMER,
        phase_before=machine.phase,
        phase_after=next_machine.phase,
    )


def request_materialization_field(
    state: ExecutionState,
    config: ExecutionConfig,
) -> TransitionResult:
    """Request evaluator WHNF demand for a materialization field."""

    machine = state.machine_state
    progress = machine.result_state.materialization

    if (
        machine.machine_kind is not MachineKind.CORE
        or machine.strategy is not config.strategy
        or machine.status is not ExecutionStatus.RUNNING
        or machine.phase is not ExecutionPhase.RESULT_MATERIALIZATION
        or not isinstance(machine.control, Return)
        or machine.stack.depth != 0
    ):
        raise InvalidResultObservationError(
            "Materialization is not at a field-demand boundary"
        )

    if (
        progress is None
        or not progress.awaiting_whnf
        or progress.pending_reference is None
        or progress.root_reference != machine.control.reference
    ):
        raise InvalidResultObservationError(
            "No pending materialization field demand"
        )

    snapshot = state.snapshot()
    next_machine = snapshot.machine_state
    stack_recorder = StackEffectRecorder()

    with next_machine.stack.capture_effects(
        stack_recorder.record
    ):
        next_machine.stack.push(
            MaterializationDemandFrame(
                root_reference=progress.root_reference,
                return_environment=next_machine.local_environment,
            )
        )

    next_machine = replace(
        next_machine,
        control=Force(progress.pending_reference),
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
        rule_id=RuleId.RESULT_MATERIALIZE_REQUEST_FIELD_WHNF,
        transition_kind=TransitionKind.RESULT_CONSUMER,
        phase_before=machine.phase,
        phase_after=next_machine.phase,
        stack_effects=stack_recorder.freeze(),
    )
