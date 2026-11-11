
"""Pure reduction of runtime instrumentation records."""

from __future__ import annotations

from dataclasses import replace

from .effects import (
    HeapAllocated,
    HeapReplaced,
    HeapBaselineRecorded,
    StackPushed,
    StackPopped,
)
from lazy_lab.runtime.state import ExecutionPhase
from lazy_lab.runtime.transitions import (
    TransitionKind,
    TransitionResult,
)

from .events import SemanticEventKind
from .state import InstrumentationState


_CORE_EVENT_COUNTERS = {
    SemanticEventKind.FUNCTION_APPLIED:
        "function_applications",
    SemanticEventKind.BETA_REDUCED:
        "beta_reductions",
    SemanticEventKind.LET_ACTIVATED:
        "let_reductions",
    SemanticEventKind.PRIMITIVE_REDUCED:
        "primitive_reductions",
    SemanticEventKind.CONDITIONAL_SELECTED:
        "conditional_reductions",
    SemanticEventKind.CASE_ALTERNATIVE_SELECTED:
        "case_reductions",
    SemanticEventKind.SEQ_REDUCED:
        "seq_reductions",
    SemanticEventKind.VARIABLE_LOOKED_UP:
        "variable_lookups",
}

_CBNEED_EVENT_COUNTERS = {
    SemanticEventKind.THUNK_CREATED:
        "thunks_created",
    SemanticEventKind.THUNK_DEMANDED:
        "thunk_demands",
    SemanticEventKind.THUNK_FORCE_STARTED:
        "thunks_forced",
    SemanticEventKind.THUNK_UPDATED:
        "thunks_updated",
    SemanticEventKind.SHARED_RESULT_HIT:
        "shared_result_hits",
    SemanticEventKind.BLACKHOLE_DETECTED:
        "blackholes",
}


def reduce_metrics(
    previous: InstrumentationState,
    transition: TransitionResult,
) -> InstrumentationState:
    """Return updated metrics without mutating input state."""
    counters = previous.counters
    increments: dict[str, int] = {}

    def bump(field_name: str) -> None:
        increments[field_name] = (
            increments.get(field_name, 0) + 1
        )

    if transition.transition_kind is TransitionKind.EVALUATOR:
        bump("evaluator_transitions")

        if (
            transition.phase_before
            is ExecutionPhase.RESULT_MATERIALIZATION
        ):
            bump("result_demand_evaluator_transitions")

    elif (
        transition.transition_kind
        is TransitionKind.RESULT_CONSUMER
    ):
        bump("result_consumer_transitions")
    
    for event in transition.semantic_events:
        field_name = _CORE_EVENT_COUNTERS.get(event.kind)

        if field_name is None:
            field_name = _CBNEED_EVENT_COUNTERS.get(
                event.kind
            )

        if field_name is not None:
            bump(field_name)

    current_slots = counters.current_heap_slots
    peak_slots = counters.peak_heap_slots
    baseline_slots = previous.baseline_slots

    pushes = counters.pushes
    pops = counters.pops
    peak_frames = counters.peak_frames

    # Heap effects are processed in operational order.
    for effect in transition.heap_effects:
        if isinstance(effect, HeapAllocated):
            if effect.allocated_slots < 1:
                raise ValueError(
                    "Allocation requires positive slots"
                )

            bump("total_allocations")
            current_slots += effect.allocated_slots
            peak_slots = max(peak_slots, current_slots)

        elif isinstance(effect, HeapReplaced):
            # Replacements preserve the allocated capacity.
            pass

        elif isinstance(effect, HeapBaselineRecorded):
            if baseline_slots is not None:
                raise ValueError(
                    "Heap baseline already recorded"
                )
            if effect.slots < 0:
                raise ValueError(
                    "Heap baseline cannot be negative"
                )

            baseline_slots = effect.slots

    # Stack effects are processed in operational order.
    for effect in transition.stack_effects:
        if isinstance(effect, StackPushed):
            pushes += 1
            peak_frames = max(
                peak_frames,
                pushes - pops,
            )

        elif isinstance(effect, StackPopped):
            if pushes == pops:
                raise ValueError(
                    "Stack accounting underflow"
                )
            pops += 1

    updates = {
        name: getattr(counters, name) + amount
        for name, amount in increments.items()
    }

    updates.update(
        current_heap_slots=current_slots,
        peak_heap_slots=peak_slots,
        pushes=pushes,
        pops=pops,
        peak_frames=peak_frames,
    )

    updated_counters = replace(counters, **updates)

    return replace(
        previous,
        counters=updated_counters,
        baseline_slots=baseline_slots,
    )

