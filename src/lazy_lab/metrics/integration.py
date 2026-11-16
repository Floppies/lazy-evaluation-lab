
"""Attach accumulated instrumentation to machine transitions."""

from __future__ import annotations

from dataclasses import replace

from lazy_lab.metrics.reducer import reduce_metrics
from lazy_lab.runtime.state import ExecutionState
from lazy_lab.runtime.transitions import TransitionResult


def accumulate_transition_metrics(
    previous_state: ExecutionState,
    transition: TransitionResult,
) -> TransitionResult:
    """Attach reduced metrics to the successor state."""

    next_metrics = reduce_metrics(
        previous_state.instrumentation_state,
        transition,
    )

    next_state = replace(
        transition.next_state,
        instrumentation_state=next_metrics,
    )

    return replace(
        transition,
        next_state=next_state,
    )
