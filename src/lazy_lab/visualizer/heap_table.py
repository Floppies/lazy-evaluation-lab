
"""Passive table projection of the simulated heap."""

from __future__ import annotations

from lazy_lab.runtime.closures import Closure
from lazy_lab.runtime.constructors import ConstructorValue
from lazy_lab.runtime.global_bindings import PendingGlobal
from lazy_lab.runtime.heap import (
    HeapObject,
    Indirection,
    Reserved,
)
from lazy_lab.runtime.predefined import (
    PredefinedFunction,
    PartialPredefinedFunction,
)
from lazy_lab.runtime.state import ExecutionState
from lazy_lab.runtime.thunks import (
    EvaluatingThunk,
    PendingThunk,
    ThunkPayload,
)
from lazy_lab.visualizer.projections import (
    project_runtime_reference,
)


def _project_heap_object_details(
    value: HeapObject,
) -> dict[str, object]:
    """Describe one stored object without evaluating it."""

    if isinstance(value, Reserved):
        return {}

    if isinstance(value, Indirection):
        return {
            "target": project_runtime_reference(value.target),
            "from_thunk_update": value.from_thunk_update,
        }

    if isinstance(value, PendingGlobal):
        return {
            "expression_kind": type(value.expression).__name__,
        }

    if isinstance(value, ThunkPayload):
        return {
            "expression_kind": type(value.expression).__name__,
            "captured_local_names": sorted(
                value.captured_locals.bindings
            ),
        }

    if isinstance(value, (PendingThunk, EvaluatingThunk)):
        return {
            "payload_reference": project_runtime_reference(
                value.payload_reference
            ),
        }

    if isinstance(value, Closure):
        return {
            "parameter": value.lambda_expression.parameter,
            "captured_local_names": sorted(
                value.captured_locals.bindings
            ),
        }

    if isinstance(value, ConstructorValue):
        return {
            "tag": value.tag,
            "arity": len(value.fields),
            "fields": [
                project_runtime_reference(reference)
                for reference in value.fields
            ],
        }

    if isinstance(value, PredefinedFunction):
        return {
            "name": value.name,
            "arity": value.arity,
        }

    if isinstance(value, PartialPredefinedFunction):
        return {
            "name": value.name,
            "arity": value.arity,
            "remaining_arity": value.remaining_arity,
            "applied_arguments": [
                project_runtime_reference(reference)
                for reference in value.applied_arguments
            ],
        }

    raise TypeError(
        f"Unsupported heap object: {type(value).__name__}"
    )

def project_heap_table(
    state: ExecutionState,
) -> dict[str, object]:
    """Project stored heap cells without modifying the machine."""

    if not isinstance(state, ExecutionState):
        raise TypeError("Expected an ExecutionState")

    heap = state.machine_state.heap
    rows: list[dict[str, object]] = []

    # Deterministic order by stable ObjectId.
    for object_id, cell in sorted(
        heap.cells.items(),
        key=lambda item: int(item[0]),
    ):
        value = cell.value

        rows.append({
            "object_id": int(object_id),
            "kind": type(value).__name__,
            "allocated_slots": cell.allocated_slots,
            "required_slots": value.required_slots,
            "details": _project_heap_object_details(value),
        })

    return {
        "transition_index": state.transition_index,
        "object_count": len(rows),
        "current_slots": heap.current_slots,
        "next_object_id": heap.next_object_id,
        "cells": rows,
    }
