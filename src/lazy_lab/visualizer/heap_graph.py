
"""Passive memory graph projection for simulated heap objects."""

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
    PartialPredefinedFunction,
    PredefinedFunction,
)
from lazy_lab.runtime.references import HeapReference
from lazy_lab.runtime.state import ExecutionState
from lazy_lab.runtime.thunks import (
    EvaluatingThunk,
    PendingThunk,
    ThunkPayload,
)
from lazy_lab.visualizer.heap_table import project_heap_table


def _outgoing_heap_references(
    value: HeapObject,
) -> tuple[tuple[str, HeapReference], ...]:
    """Collect explicit heap references without following them."""

    result: list[tuple[str, HeapReference]] = []

    def add(role: str, reference: object) -> None:
        if isinstance(reference, HeapReference):
            result.append((role, reference))

    if isinstance(value, (PendingThunk, EvaluatingThunk)):
        add("payload_reference", value.payload_reference)

    elif isinstance(value, Indirection):
        add("target", value.target)

    elif isinstance(value, ConstructorValue):
        for index, reference in enumerate(value.fields):
            add(f"fields[{index}]", reference)

    elif isinstance(value, (ThunkPayload, Closure)):
        for name, reference in sorted(
            value.captured_locals.bindings.items()
        ):
            add(f"captured_locals.{name}", reference)

    elif isinstance(value, PartialPredefinedFunction):
        for index, reference in enumerate(
            value.applied_arguments
        ):
            add(f"applied_arguments[{index}]", reference)

    elif isinstance(
        value,
        (Reserved, PendingGlobal, PredefinedFunction),
    ):
        pass

    else:
        raise TypeError(
            f"Unsupported heap object: {type(value).__name__}"
        )

    return tuple(result)

def project_memory_graph(
    state: ExecutionState,
) -> dict[str, object]:
    """Build a read-only graph of the stored heap references."""

    if not isinstance(state, ExecutionState):
        raise TypeError("Expected an ExecutionState")

    table = project_heap_table(state)
    heap = state.machine_state.heap

    nodes = [
        {
            "object_id": row["object_id"],
            "kind": row["kind"],
            "allocated_slots": row["allocated_slots"],
            "required_slots": row["required_slots"],
        }
        for row in table["cells"]
    ]

    edges: list[dict[str, object]] = []

    for object_id, cell in sorted(
        heap.cells.items(),
        key=lambda item: int(item[0]),
    ):
        for role, reference in _outgoing_heap_references(
            cell.value
        ):
            edges.append({
                "source_object_id": int(object_id),
                "target_object_id": int(reference.object_id),
                "role": role,
            })

    return {
        "transition_index": state.transition_index,
        "nodes": nodes,
        "edges": edges,
    }
