
"""Passive differences between retained heap snapshots."""

from __future__ import annotations

from lazy_lab.runtime.heap import HeapCell
from lazy_lab.runtime.state import ExecutionState


def _cell_summary(cell: HeapCell) -> dict[str, object]:
    """Describe a heap cell without traversing its contents."""

    return {
        "kind": type(cell.value).__name__,
        "allocated_slots": cell.allocated_slots,
        "required_slots": cell.value.required_slots,
    }

def project_heap_snapshot_diff(
    previous: ExecutionState,
    current: ExecutionState,
) -> dict[str, object]:
    """Compare two ordered states from the same in-memory session.

    Object identity detects replacements because Heap.clone()
    shares immutable HeapObject values between snapshots.

    The result describes net snapshot differences, not events.
    """

    if not isinstance(previous, ExecutionState):
        raise TypeError("Expected an ExecutionState for previous")

    if not isinstance(current, ExecutionState):
        raise TypeError("Expected an ExecutionState for current")

    if previous.session_id != current.session_id:
        raise ValueError(
            "Cannot compare states from different sessions"
        )

    if previous.transition_index >= current.transition_index:
        raise ValueError(
            "Snapshots must be ordered by increasing transition index"
        )

    previous_heap = previous.machine_state.heap
    current_heap = current.machine_state.heap

    previous_cells = previous_heap.cells
    current_cells = current_heap.cells

    object_ids = sorted(
        set(previous_cells) | set(current_cells),
        key=int,
    )

    changes: list[dict[str, object]] = []
    unchanged_count = 0

    for object_id in object_ids:
        before = previous_cells.get(object_id)
        after = current_cells.get(object_id)

        if before is None:
            change = "created"

        elif after is None:
            change = "removed"

        elif (
            before.value is not after.value
            or before.allocated_slots != after.allocated_slots
        ):
            change = "updated"

        else:
            unchanged_count += 1
            continue

        changes.append({
            "object_id": int(object_id),
            "change": change,
            "before": (
                _cell_summary(before)
                if before is not None
                else None
            ),
            "after": (
                _cell_summary(after)
                if after is not None
                else None
            ),
        })

    counts = {
        "created": sum(
            item["change"] == "created"
            for item in changes
        ),
        "updated": sum(
            item["change"] == "updated"
            for item in changes
        ),
        "removed": sum(
            item["change"] == "removed"
            for item in changes
        ),
        "unchanged": unchanged_count,
    }

    return {
        "session_id": current.session_id,
        "from_state_id": previous.state_id,
        "to_state_id": current.state_id,
        "from_transition_index": previous.transition_index,
        "to_transition_index": current.transition_index,
        "adjacent": (
            current.transition_index
            == previous.transition_index + 1
        ),
        "heap_slots": {
            "before": previous_heap.current_slots,
            "after": current_heap.current_slots,
            "delta": (
                current_heap.current_slots
                - previous_heap.current_slots
            ),
        },
        "counts": counts,
        "changes": changes,
    }
