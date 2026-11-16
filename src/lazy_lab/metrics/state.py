
"""Immutable accumulated state for runtime metrics."""

from __future__ import annotations

from dataclasses import dataclass, field, fields


@dataclass(frozen=True, slots=True)
class MetricCounters:
    # Transition accounting
    evaluator_transitions: int = 0
    result_demand_evaluator_transitions: int = 0
    result_consumer_transitions: int = 0
    result_nodes: int = 0

    # Core semantic work
    function_applications: int = 0
    beta_reductions: int = 0
    let_reductions: int = 0
    primitive_reductions: int = 0
    conditional_reductions: int = 0
    case_reductions: int = 0
    seq_reductions: int = 0
    variable_lookups: int = 0

    # Heap accounting
    total_allocations: int = 0
    current_heap_slots: int = 0
    peak_heap_slots: int = 0

    # Explicit stack accounting
    pushes: int = 0
    pops: int = 0
    peak_frames: int = 0

    # Call-by-Need accounting
    thunks_created: int = 0
    thunk_demands: int = 0
    thunks_forced: int = 0
    thunks_updated: int = 0
    shared_result_hits: int = 0
    blackholes: int = 0
    current_thunk_chain_length: int = 0
    max_thunk_chain_length: int = 0

    def __post_init__(self) -> None:
        for metric in fields(self):
            value = getattr(self, metric.name)
            if type(value) is not int or value < 0:
                raise ValueError(
                    f"{metric.name} must be a "
                    "non-negative integer"
                )

    @property
    def semantic_reductions(self) -> int:
        return (
            self.beta_reductions
            + self.let_reductions
            + self.primitive_reductions
            + self.conditional_reductions
            + self.case_reductions
            + self.seq_reductions
        )

    @property
    def current_frames(self) -> int:
        return self.pushes - self.pops

    @property
    def thunks_never_forced(self) -> int:
        return self.thunks_created - self.thunks_forced


@dataclass(frozen=True, slots=True)
class InstrumentationState:
    counters: MetricCounters = field(
        default_factory=MetricCounters
    )
    baseline_slots: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.counters, MetricCounters):
            raise TypeError(
                "counters must be MetricCounters"
            )

        if self.baseline_slots is not None:
            if (
                type(self.baseline_slots) is not int
                or self.baseline_slots < 0
            ):
                raise ValueError(
                    "baseline_slots must be non-negative"
                )

    @property
    def additional_peak_over_baseline(self) -> int | None:
        if self.baseline_slots is None:
            return None

        return max(
            0,
            self.counters.peak_heap_slots
            - self.baseline_slots,
        )
