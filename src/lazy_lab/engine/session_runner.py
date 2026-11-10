
"""Coordinate evaluator and result-consumer batches."""

from __future__ import annotations

from lazy_lab.engine.core_machine import run_batch
from lazy_lab.engine.result_consumer import (
    advance_constructor_materialization,
    complete_constructor_materialization,
    consume_whnf_result,
    consume_materialized_result,
    InvalidResultObservationError,
    finish_limited_materialization,
    request_materialization_field,
    start_constructor_materialization,
)
from lazy_lab.runtime.constructors import ConstructorValue
from lazy_lab.runtime.control import Return
from lazy_lab.runtime.references import HeapReference
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionPhase,
    ExecutionState,
    ExecutionStatus,
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
    """Run at most max_steps evaluator and consumer transitions."""
    if type(max_steps) is not int or max_steps < 1:
        raise ValueError("max_steps must be a positive integer")

    current = state
    trace: list[TraceEntry] = []

    while True:
        machine = current.machine_state
        if machine.status is not ExecutionStatus.RUNNING:
            return BatchResult(current, tuple(trace), BatchStopReason.TERMINAL_STATUS)

        remaining = max_steps - (current.transition_index - state.transition_index)
        if remaining <= 0:
            return BatchResult(current, tuple(trace), BatchStopReason.BATCH_LIMIT)

        if machine.phase is ExecutionPhase.RESULT_MATERIALIZATION:
            progress = machine.result_state.materialization
            if progress is None:
                raise InvalidResultObservationError("Missing materialization state")

            if machine.stack.depth > 0:
                evaluated = run_batch(current, config, max_steps=remaining)
                current = evaluated.state
                trace.extend(evaluated.trace)

                if evaluated.stop_reason is BatchStopReason.WHNF_PENDING:
                    continue
                if evaluated.stop_reason is BatchStopReason.EVALUATOR_BUDGET:
                    if current.transition_index - state.transition_index >= max_steps:
                        return BatchResult(current, tuple(trace), BatchStopReason.BATCH_LIMIT)
                    transition = finish_limited_materialization(current, config)
                else:
                    return BatchResult(current, tuple(trace), evaluated.stop_reason)

            elif progress.completed_value is not None:
                transition = complete_constructor_materialization(current, config)
            elif progress.limit_reached:
                transition = finish_limited_materialization(current, config)
            elif progress.awaiting_whnf:
                if machine.evaluator_transition_count >= config.execution_step_limit:
                    transition = finish_limited_materialization(current, config)
                else:
                    transition = request_materialization_field(current, config)
            else:
                transition = advance_constructor_materialization(current, config)

        else:
            evaluated = run_batch(current, config, max_steps=remaining)
            current = evaluated.state
            trace.extend(evaluated.trace)
            if evaluated.stop_reason is not BatchStopReason.WHNF_PENDING:
                return BatchResult(current, tuple(trace), evaluated.stop_reason)

            machine = current.machine_state
            mode = (
                machine.result_state.resolved_result_mode
                if config.result_policy is ResultPolicy.ASK_AT_WHNF
                else config.result_policy
            )
            if mode is None:
                return BatchResult(current, tuple(trace), BatchStopReason.WHNF_PENDING)

            if current.transition_index - state.transition_index >= max_steps:
                return BatchResult(current, tuple(trace), BatchStopReason.BATCH_LIMIT)

            if mode is ResultPolicy.WHNF_ONLY:
                transition = consume_whnf_result(current, config)
            elif mode is ResultPolicy.MATERIALIZE_COMPLETE_VALUE:
                reference = machine.control.reference
                is_constructor = (
                    isinstance(machine.control, Return)
                    and isinstance(reference, HeapReference)
                    and isinstance(machine.heap.get(reference).value, ConstructorValue)
                )
                transition = (
                    start_constructor_materialization(current, config)
                    if is_constructor
                    else consume_materialized_result(current, config)
                )
            else:
                raise InvalidResultObservationError("Unsupported result mode")

        current = transition.next_state
        if config.trace_mode is not TraceMode.METRICS_ONLY:
            trace.append(TraceEntry.from_transition(transition))