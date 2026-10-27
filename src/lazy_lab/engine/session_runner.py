
"""Coordinate evaluator and result-consumer batches."""

from __future__ import annotations

from lazy_lab.engine.core_machine import run_batch
from lazy_lab.engine.result_consumer import (
    consume_whnf_result,
    consume_materialized_result,
    InvalidResultObservationError,
)
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionState,
    ResultPolicy,
    TraceMode,
)
from lazy_lab.runtime.transitions import (
    BatchResult,
    BatchStopReason,
    TraceEntry,
)


def run_session_batch(
    state: ExecutionState,
    config: ExecutionConfig,
    *,
    max_steps: int,
) -> BatchResult:
    """Run evaluator work and, when possible, consume its result.

    max_steps limits total transitions in this batch,
    including administrative result-consumer transitions.
    """

    if type(max_steps) is not int or max_steps < 1:
        raise ValueError(
            "max_steps must be a positive integer"
        )

    # Existing evaluator batch handles configuration checks,
    # terminal states, evaluator budgets and WHNF detection.
    evaluated = run_batch(
        state,
        config,
        max_steps=max_steps,
    )

    if evaluated.stop_reason is not BatchStopReason.WHNF_PENDING:
        return evaluated

    current = evaluated.state
    machine = current.machine_state

    # An unresolved ASK_AT_WHNF is a controller decision.
    # No transition occurs while waiting.
    if config.result_policy is ResultPolicy.ASK_AT_WHNF:
        selected_mode = (
            machine.result_state.resolved_result_mode
        )

        if selected_mode is None:
            return evaluated

    else:
        selected_mode = config.result_policy

    # How many transitions have been consumed in this batch?
    # This must work even when tracing is disabled.
    used_steps = (
        current.transition_index - state.transition_index
    )
    remaining_steps = max_steps - used_steps

    if remaining_steps <= 0:
        return BatchResult(
            state=current,
            trace=evaluated.trace,
            stop_reason=BatchStopReason.BATCH_LIMIT,
        )

    if selected_mode is ResultPolicy.WHNF_ONLY:
        transition = consume_whnf_result(
            current,
            config,
        )

    elif selected_mode is ResultPolicy.MATERIALIZE_COMPLETE_VALUE:
        transition = consume_materialized_result(
            current,
            config,
        )

    else:
        raise InvalidResultObservationError(
            "Unsupported resolved result mode"
        )

    trace = list(evaluated.trace)

    if config.trace_mode is not TraceMode.METRICS_ONLY:
        trace.append(
            TraceEntry.from_transition(transition)
        )

    return BatchResult(
        state=transition.next_state,
        trace=tuple(trace),
        stop_reason=BatchStopReason.TERMINAL_STATUS,
    )
