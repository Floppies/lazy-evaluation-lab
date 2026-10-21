"""Minimal small-step transitions for Core literals."""

from __future__ import annotations

from dataclasses import replace

from lazy_lab.core.nodes import CoreBool, CoreInt, CoreExpr

from lazy_lab.runtime.control import EvaluateCore, Return
from lazy_lab.runtime.references import (
    ImmediateBoolean,
    ImmediateInteger,
)
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionState,
    ExecutionStatus,
    MachineKind,
    TraceMode,
)
from lazy_lab.runtime.transitions import (
    BatchResult,
    BatchStopReason,
    TraceEntry,
    TransitionKind,
    TransitionResult,
)


class UnsupportedTransitionError(NotImplementedError):
    """The requested transition is not implemented yet."""


class InvalidMachineStateError(RuntimeError):
    """The current state cannot be advanced."""


class EvaluatorBudgetExhaustedError(RuntimeError):
    """No evaluator transitions remain in the execution budget."""


def _validate_configuration(
    state: ExecutionState,
    config: ExecutionConfig,
) -> None:
    machine = state.machine_state

    if (
        machine.machine_kind is not config.machine_kind
        or machine.strategy is not config.strategy
    ):
        raise ValueError(
            "Execution configuration does not match the machine"
        )

    if machine.machine_kind is not MachineKind.CORE:
        raise UnsupportedTransitionError(
            "STG execution is not implemented yet"
        )

def _evaluate_integer(
    expression: CoreInt,
) -> tuple[Return, str]:
    """Apply the Core integer literal rule."""
    return (
        Return(ImmediateInteger(expression.value)),
        "CORE_EVAL_INTEGER",
    )


def _evaluate_boolean(
    expression: CoreBool,
) -> tuple[Return, str]:
    """Apply the Core boolean literal rule."""
    return (
        Return(ImmediateBoolean(expression.value)),
        "CORE_EVAL_BOOLEAN",
    )


def _dispatch_core_evaluation(
    expression: CoreExpr,
) -> tuple[Return, str]:
    """Select one of the currently supported Core rules."""
    if isinstance(expression, CoreInt):
        return _evaluate_integer(expression)

    if isinstance(expression, CoreBool):
        return _evaluate_boolean(expression)

    raise UnsupportedTransitionError(
        f"Unsupported Core expression: "
        f"{type(expression).__name__}"
    )


def step(
    state: ExecutionState,
    config: ExecutionConfig,
) -> TransitionResult:
    """Apply one supported Core evaluation transition."""
    _validate_configuration(state, config)

    machine = state.machine_state

    if machine.status is not ExecutionStatus.RUNNING:
        raise InvalidMachineStateError(
            "Only RUNNING states can advance"
        )

    control = machine.control

    if not isinstance(control, EvaluateCore):
        raise UnsupportedTransitionError(
            f"Unsupported control: {type(control).__name__}"
        )

    if (
        machine.evaluator_transition_count
        >= config.execution_step_limit
    ):
        raise EvaluatorBudgetExhaustedError(
            "Evaluator step limit reached"
        )

    # Rule selection and application.
    next_control, rule_id = _dispatch_core_evaluation(
        control.expression
    )

    # Construct an independent successor state.
    snapshot = state.snapshot()

    next_machine = replace(
        snapshot.machine_state,
        control=next_control,
        evaluator_transition_count=(
            machine.evaluator_transition_count + 1
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
        rule_id=rule_id,
        transition_kind=TransitionKind.EVALUATOR,
        phase_before=machine.phase,
        phase_after=next_machine.phase,
    )

def _stop_reason(
    state: ExecutionState,
    config: ExecutionConfig,
) -> BatchStopReason | None:
    machine = state.machine_state

    if machine.status is not ExecutionStatus.RUNNING:
        return BatchStopReason.TERMINAL_STATUS

    if (
        isinstance(machine.control, Return)
        and machine.stack.depth == 0
    ):
        return BatchStopReason.WHNF_PENDING

    if (
        machine.evaluator_transition_count
        >= config.execution_step_limit
    ):
        return BatchStopReason.EVALUATOR_BUDGET

    return None

def run_batch(
    state: ExecutionState,
    config: ExecutionConfig,
    *,
    max_steps: int,
) -> BatchResult:
    """Execute a bounded batch of supported transitions."""
    if type(max_steps) is not int or max_steps < 1:
        raise ValueError("max_steps must be a positive integer")

    _validate_configuration(state, config)

    current = state
    entries: list[TraceEntry] = []

    for _ in range(max_steps):
        reason = _stop_reason(current, config)

        if reason is not None:
            return BatchResult(
                state=current,
                trace=tuple(entries),
                stop_reason=reason,
            )

        transition = step(current, config)
        current = transition.next_state

        if config.trace_mode is not TraceMode.METRICS_ONLY:
            entries.append(
                TraceEntry.from_transition(transition)
            )

    return BatchResult(
        state=current,
        trace=tuple(entries),
        stop_reason=(
            _stop_reason(current, config)
            or BatchStopReason.BATCH_LIMIT
        ),
    )

