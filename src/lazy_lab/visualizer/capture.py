
"""Pure classification of transitions for selective capture."""

from __future__ import annotations

from lazy_lab.metrics.effects import HeapAllocated, HeapReplaced
from lazy_lab.metrics.events import SemanticEventKind
from lazy_lab.runtime.state import ExecutionPhase
from lazy_lab.runtime.transitions import TransitionResult


SUPPORTED_CAPTURE_CATEGORIES = frozenset({
    "thunks",
    "materialization",
    "heap",
    "stack",
    "reductions",
})


THUNK_EVENTS = frozenset({
    SemanticEventKind.THUNK_CREATED,
    SemanticEventKind.THUNK_DEMANDED,
    SemanticEventKind.THUNK_FORCE_STARTED,
    SemanticEventKind.THUNK_UPDATED,
    SemanticEventKind.SHARED_RESULT_HIT,
    SemanticEventKind.BLACKHOLE_DETECTED,
})


REDUCTION_EVENTS = frozenset({
    SemanticEventKind.BETA_REDUCED,
    SemanticEventKind.LET_ACTIVATED,
    SemanticEventKind.PRIMITIVE_REDUCED,
    SemanticEventKind.CONDITIONAL_SELECTED,
    SemanticEventKind.CASE_ALTERNATIVE_SELECTED,
    SemanticEventKind.SEQ_REDUCED,
})


def validate_capture_categories(
    categories: frozenset[str],
) -> None:
    """Validate the supported B08 capture category names."""

    if not isinstance(categories, frozenset):
        raise TypeError(
            "Capture categories must be a frozenset"
        )

    if any(type(category) is not str for category in categories):
        raise ValueError(
            "Capture categories must contain strings"
        )

    unknown = categories - SUPPORTED_CAPTURE_CATEGORIES

    if unknown:
        raise ValueError(
            "Unsupported capture categories: "
            + ", ".join(sorted(unknown))
        )

def matching_capture_categories(
    transition: TransitionResult,
    selected_categories: frozenset[str],
) -> frozenset[str]:
    """Return selected categories matching a transition."""

    if not isinstance(transition, TransitionResult):
        raise TypeError("Expected a TransitionResult")

    validate_capture_categories(selected_categories)

    if not selected_categories:
        return frozenset()

    matched: set[str] = set()

    event_kinds = {
        event.kind
        for event in transition.semantic_events
    }

    if (
        "thunks" in selected_categories
        and event_kinds & THUNK_EVENTS
    ):
        matched.add("thunks")

    if (
        "materialization" in selected_categories
        and (
            transition.phase_before
            is ExecutionPhase.RESULT_MATERIALIZATION
            or transition.phase_after
            is ExecutionPhase.RESULT_MATERIALIZATION
        )
    ):
        matched.add("materialization")

    if (
        "heap" in selected_categories
        and any(
            isinstance(effect, (HeapAllocated, HeapReplaced))
            for effect in transition.heap_effects
        )
    ):
        matched.add("heap")

    if (
        "stack" in selected_categories
        and transition.stack_effects
    ):
        matched.add("stack")

    if (
        "reductions" in selected_categories
        and event_kinds & REDUCTION_EVENTS
    ):
        matched.add("reductions")

    return frozenset(matched)
