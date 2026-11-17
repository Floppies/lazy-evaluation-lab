
"""Passive, JSON-compatible projections of execution states."""

from __future__ import annotations

from dataclasses import fields, is_dataclass

from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionState,
)
from lazy_lab.core.nodes import CoreAlt, CoreBinding, CoreExpr
from lazy_lab.runtime.control import InitializeLocalBindings
from lazy_lab.runtime.environment import Environment
from lazy_lab.runtime.references import (
    HeapReference,
    ImmediateBoolean,
    ImmediateInteger,
)


def _project_reference(
    reference: HeapReference | ImmediateInteger | ImmediateBoolean,
) -> dict[str, object]:
    """Describe a runtime reference without accessing the heap."""

    if isinstance(reference, HeapReference):
        return {
            "kind": "heap",
            "object_id": int(reference.object_id),
        }

    if isinstance(reference, ImmediateInteger):
        return {
            "kind": "integer",
            "value": reference.value,
        }

    if isinstance(reference, ImmediateBoolean):
        return {
            "kind": "boolean",
            "value": reference.value,
        }

    raise TypeError("Unsupported runtime reference")

def _project_shallow_value(value: object) -> object:
    """Project one control/frame field without recursive traversal."""

    if value is None or type(value) in (str, int, bool):
        return value

    if isinstance(
        value,
        (HeapReference, ImmediateInteger, ImmediateBoolean),
    ):
        return _project_reference(value)

    if isinstance(value, Environment):
        return {
            "kind": "Environment",
            "local_binding_count": len(value.bindings),
            "has_parent": value.parent is not None,
        }

    if isinstance(value, InitializeLocalBindings):
        return {
            "kind": "InitializeLocalBindings",
            "binding_count": len(value.bindings),
            "next_index": value.next_index,
            "body_kind": type(value.body).__name__,
        }

    if isinstance(value, CoreExpr):
        return {
            "kind": type(value).__name__,
        }

    if isinstance(value, CoreAlt):
        return {
            "kind": type(value).__name__,
        }

    if isinstance(value, CoreBinding):
        return {
            "kind": "CoreBinding",
            "name": value.name,
        }

    if isinstance(value, tuple):
        references = (
            HeapReference,
            ImmediateInteger,
            ImmediateBoolean,
        )

        if value and all(
            isinstance(item, references)
            for item in value
        ):
            return {
                "count": len(value),
                "references": [
                    _project_reference(item)
                    for item in value
                ],
            }

        return {
            "count": len(value),
        }

    raise TypeError(
        "Unsupported projection field type: "
        f"{type(value).__name__}"
    )

def _project_record(record: object) -> dict[str, object]:
    """Project a known control or stack-frame dataclass."""

    if not is_dataclass(record) or isinstance(record, type):
        raise TypeError("Expected a control or stack-frame record")

    return {
        "kind": type(record).__name__,
        "fields": {
            item.name: _project_shallow_value(
                getattr(record, item.name)
            )
            for item in fields(record)
        },
    }

def project_control_and_stack(
    state: ExecutionState,
) -> dict[str, object]:
    """Project the current control and ordered continuation stack."""

    if not isinstance(state, ExecutionState):
        raise TypeError("Expected an ExecutionState")

    machine = state.machine_state
    frames = machine.stack.frames

    return {
        "control": _project_record(machine.control),
        "stack": {
            "depth": machine.stack.depth,
            "frames": [
                {
                    "position": index,
                    "is_top": index == len(frames) - 1,
                    **_project_record(frame),
                }
                for index, frame in enumerate(frames)
            ],
        },
    }

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
