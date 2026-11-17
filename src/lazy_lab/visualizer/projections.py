
"""Passive, JSON-compatible projections of execution states."""

from __future__ import annotations

from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionState,
)


def project_execution_overview(
    state: ExecutionState,
    config: ExecutionConfig,
) -> dict[str, object]:
    """Project execution metadata without modifying machine state."""

    if not isinstance(state, ExecutionState):
        raise TypeError("Expected an ExecutionState")

    if not isinstance(config, ExecutionConfig):
        raise TypeError("Expected an ExecutionConfig")

    machine = state.machine_state

    if (
        machine.machine_kind is not config.machine_kind
        or machine.strategy is not config.strategy
    ):
        raise ValueError(
            "Execution configuration does not match the machine"
        )

    result_state = machine.result_state

    return {
        "session_id": state.session_id,
        "state_id": state.state_id,
        "transition_index": state.transition_index,
        "config": {
            "machine_kind": config.machine_kind.value,
            "strategy": config.strategy.value,
            "result_policy": config.result_policy.value,
            "execution_step_limit": config.execution_step_limit,
            "result_node_limit": config.result_node_limit,
            "trace_mode": config.trace_mode.value,
        },
        "machine": {
            "status": machine.status.value,
            "phase": machine.phase.value,
            "control_kind": type(machine.control).__name__,
            "evaluator_transition_count": (
                machine.evaluator_transition_count
            ),
            "stack_depth": machine.stack.depth,
            "heap_slots": machine.heap.current_slots,
            "heap_objects": len(machine.heap.cells),
        },
        "result": {
            "selected_mode": (
                result_state.resolved_result_mode.value
                if result_state.resolved_result_mode is not None
                else None
            ),
            "canonical_result_available": (
                state.canonical_result is not None
            ),
        },
    }
