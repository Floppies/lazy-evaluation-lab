"""Persistent, iterative canonical materialization state."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .constructors import ConstructorValue
from .heap import Heap
from .observation import (
    CanonicalConstructor,
    CanonicalPartialConstructor,
    CanonicalPending,
    CanonicalValue,
    ConstructorWHNF,
    PartialCanonicalValue,
    UnresolvedObservationError,
    observe_whnf,
)
from .references import HeapReference, RuntimeRef


@dataclass(frozen=True, slots=True)
class MaterializationFrame:
    """A constructor awaiting its remaining materialized fields."""

    tag: str
    remaining_fields: tuple[RuntimeRef, ...]
    completed_fields: tuple[CanonicalValue, ...] = ()


@dataclass(frozen=True, slots=True)
class MaterializationState:
    """Persistent progress of a depth-first materialization."""

    root_reference: RuntimeRef
    pending_reference: RuntimeRef | None
    frames: tuple[MaterializationFrame, ...] = ()
    completed_value: CanonicalValue | None = None
    visited_nodes: int = 0
    awaiting_whnf: bool = False


@dataclass(frozen=True, slots=True)
class MaterializationState:
    root_reference: RuntimeRef
    pending_reference: RuntimeRef | None
    frames: tuple[MaterializationFrame, ...] = ()
    completed_value: CanonicalValue | None = None
    visited_nodes: int = 0
    awaiting_whnf: bool = False

    limit_reached: bool = False
    partial_value: PartialCanonicalValue | None = None


def start_materialization(
    reference: RuntimeRef,
) -> MaterializationState:
    return MaterializationState(
        root_reference=reference,
        pending_reference=reference,
    )

def advance_materialization(
    heap: Heap,
    state: MaterializationState,
    *,
    node_limit: int | None = None,
) -> MaterializationState:
    """Visit one WHNF node and advance the explicit DFS traversal."""

    if state.completed_value is not None:
        raise ValueError("Materialization is already complete")

    if state.awaiting_whnf:
        raise ValueError("Pending WHNF demand must be resumed first")

    if state.limit_reached:
        raise ValueError("Materialization node limit already reached")

    if node_limit is not None:
        if type(node_limit) is not int or node_limit < 1:
            raise ValueError("node_limit must be a positive integer")

        if state.visited_nodes >= node_limit:
            return replace(
                state,
                limit_reached=True,
                partial_value=build_partial_value(state),
            )
    
    reference = state.pending_reference

    if reference is None:
        raise ValueError("Materialization has no pending reference")

    try:
        observed = observe_whnf(heap, reference)
    except UnresolvedObservationError:
        return replace(state, awaiting_whnf=True)

    visited_nodes = state.visited_nodes + 1

    if isinstance(observed, ConstructorWHNF):
        if not isinstance(reference, HeapReference):
            raise ValueError("Constructor must have a heap reference")

        constructor = heap.get(reference).value

        if not isinstance(constructor, ConstructorValue):
            raise ValueError("Inconsistent constructor observation")

        if constructor.fields:
            frame = MaterializationFrame(
                tag=constructor.tag,
                remaining_fields=constructor.fields[1:],
            )

            return replace(
                state,
                frames=state.frames + (frame,),
                pending_reference=constructor.fields[0],
                visited_nodes=visited_nodes,
            )

        completed = CanonicalConstructor(
            tag=constructor.tag,
            fields=(),
        )
    else:
        completed = observed

    # Attach the completed child to its parent, iteratively.
    frames = state.frames

    while frames:
        parent = frames[-1]
        completed_fields = parent.completed_fields + (completed,)

        if parent.remaining_fields:
            next_reference = parent.remaining_fields[0]

            updated_parent = replace(
                parent,
                remaining_fields=parent.remaining_fields[1:],
                completed_fields=completed_fields,
            )

            return replace(
                state,
                frames=frames[:-1] + (updated_parent,),
                pending_reference=next_reference,
                visited_nodes=visited_nodes,
            )

        completed = CanonicalConstructor(
            tag=parent.tag,
            fields=completed_fields,
        )
        frames = frames[:-1]

    return replace(
        state,
        frames=(),
        pending_reference=None,
        completed_value=completed,
        visited_nodes=visited_nodes,
    )

def resume_materialization(
    state: MaterializationState,
    whnf_reference: RuntimeRef,
) -> MaterializationState:
    """Resume traversal after the evaluator has returned WHNF."""

    if not state.awaiting_whnf:
        raise ValueError("Materialization is not awaiting WHNF")

    return replace(
        state,
        pending_reference=whnf_reference,
        awaiting_whnf=False,
    )

def build_partial_value(
    state: MaterializationState,
) -> PartialCanonicalValue:
    """Build a partial tree from the current DFS continuation."""

    if state.completed_value is not None:
        raise ValueError("Materialization is already complete")

    partial: PartialCanonicalValue = CanonicalPending()

    for frame in reversed(state.frames):
        partial = CanonicalPartialConstructor(
            tag=frame.tag,
            fields=frame.completed_fields + (partial,),
            unvisited_fields=len(frame.remaining_fields),
        )

    return partial