
"""Comparison context for completed or partial metric runs."""

from __future__ import annotations

from dataclasses import dataclass, fields

from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionState,
    ResultPolicy,
    Strategy,
)
from lazy_lab.metrics.state import MetricCounters
from lazy_lab.runtime.state import (
    ExecutionStatus,
    MachineKind,
)


@dataclass(frozen=True, slots=True)
class ComparisonRun:
    """A measured execution and its comparison context."""

    workload_id: str
    config: ExecutionConfig
    state: ExecutionState

    def __post_init__(self) -> None:
        if (
            not isinstance(self.workload_id, str)
            or not self.workload_id.strip()
        ):
            raise ValueError(
                "workload_id must be a non-empty string"
            )

        if not isinstance(self.config, ExecutionConfig):
            raise TypeError("Expected ExecutionConfig")

        if not isinstance(self.state, ExecutionState):
            raise TypeError("Expected ExecutionState")

        machine = self.state.machine_state

        if (
            machine.machine_kind is not self.config.machine_kind
            or machine.strategy is not self.config.strategy
        ):
            raise ValueError(
                "Execution configuration does not match "
                "the measured state"
            )

    @property
    def counters(self) -> MetricCounters:
        """Return the accumulated counters."""
        return self.state.instrumentation_state.counters

    @property
    def effective_result_policy(self) -> ResultPolicy | None:
        """Return the actual observation mode when resolved."""
        if self.config.result_policy is ResultPolicy.ASK_AT_WHNF:
            return (
                self.state.machine_state
                .result_state.resolved_result_mode
            )

        return self.config.result_policy


@dataclass(frozen=True, slots=True)
class ComparabilityAssessment:
    """Eligibility for comparing complete execution costs."""

    complete_costs_comparable: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MetricComparison:
    """Comparison of one explicitly named metric."""

    metric_name: str
    unit: str
    left_value: int
    right_value: int
    delta: int
    ratio: float | None
    assessment: ComparabilityAssessment


_ALLOWED_FACTORS = frozenset({
    "workload",
    "strategy",
    "result_policy",
    "execution_step_limit",
    "result_node_limit",
})


_DERIVED_METRICS = frozenset({
    "semantic_reductions",
    "current_frames",
    "thunks_never_forced",
    "additional_peak_over_baseline",
})

_AVAILABLE_METRICS = (
    frozenset(field.name for field in fields(MetricCounters))
    | _DERIVED_METRICS
)

_CBNEED_ONLY_METRICS = frozenset({
    "thunks_created",
    "thunk_demands",
    "thunks_forced",
    "thunks_updated",
    "shared_result_hits",
    "blackholes",
    "thunks_never_forced",
    "current_thunk_chain_length",
    "max_thunk_chain_length",
})

_SLOT_METRICS = frozenset({
    "current_heap_slots",
    "peak_heap_slots",
    "additional_peak_over_baseline",
})

_FRAME_METRICS = frozenset({
    "current_frames",
    "peak_frames",
    "current_thunk_chain_length",
    "max_thunk_chain_length",
})


def _metric_value(run: ComparisonRun, name: str) -> int:
    if name == "additional_peak_over_baseline":
        value = (
            run.state.instrumentation_state
            .additional_peak_over_baseline
        )

        if value is None:
            raise ValueError(
                "Metric requires a recorded heap baseline"
            )

        return value

    return getattr(run.counters, name)


def compare_metric(
    left: ComparisonRun,
    right: ComparisonRun,
    metric_name: str,
    *,
    varied_factors: frozenset[str] = frozenset(),
) -> MetricComparison:
    """Compare one metric without inventing unavailable ratios."""

    if metric_name not in _AVAILABLE_METRICS:
        raise ValueError(
            f"Unsupported metric: {metric_name!r}"
        )

    assessment = assess_comparability(
        left,
        right,
        varied_factors=varied_factors,
    )

    if metric_name in _CBNEED_ONLY_METRICS:
        if (
            left.config.strategy is not Strategy.CBNEED
            or right.config.strategy is not Strategy.CBNEED
        ):
            raise ValueError(
                "Metric is only applicable to CBNeed runs"
            )

    left_value = _metric_value(left, metric_name)
    right_value = _metric_value(right, metric_name)

    delta = left_value - right_value

    ratio = (
        left_value / right_value
        if (
            assessment.complete_costs_comparable
            and right_value > 0
        )
        else None
    )

    if metric_name in _SLOT_METRICS:
        unit = "abstract_slots"
    elif metric_name in _FRAME_METRICS:
        unit = "frames"
    elif metric_name == "result_nodes":
        unit = "nodes"
    else:
        unit = "count"

    return MetricComparison(
        metric_name=metric_name,
        unit=unit,
        left_value=left_value,
        right_value=right_value,
        delta=delta,
        ratio=ratio,
        assessment=assessment,
    )


def assess_comparability(
    left: ComparisonRun,
    right: ComparisonRun,
    *,
    varied_factors: frozenset[str] = frozenset(),
) -> ComparabilityAssessment:
    """Assess comparability of complete logical execution costs."""

    if (
        not isinstance(left, ComparisonRun)
        or not isinstance(right, ComparisonRun)
    ):
        raise TypeError("Expected ComparisonRun instances")

    unknown = varied_factors - _ALLOWED_FACTORS

    if unknown:
        raise ValueError(
            f"Unknown comparison factors: {sorted(unknown)}"
        )

    reasons: list[str] = []

    # B07 comparison currently supports Core runs only.
    if (
        left.config.machine_kind is not MachineKind.CORE
        or right.config.machine_kind is not MachineKind.CORE
    ):
        reasons.append("unsupported_machine_kind")

    dimensions = (
        ("workload", left.workload_id, right.workload_id),
        ("strategy", left.config.strategy, right.config.strategy),
        (
            "result_policy",
            left.effective_result_policy,
            right.effective_result_policy,
        ),
        (
            "execution_step_limit",
            left.config.execution_step_limit,
            right.config.execution_step_limit,
        ),
        (
            "result_node_limit",
            left.config.result_node_limit,
            right.config.result_node_limit,
        ),
    )

    for name, left_value, right_value in dimensions:
        if (
            left_value != right_value
            and name not in varied_factors
        ):
            reasons.append(f"different_{name}")

    for name, run in (("left", left), ("right", right)):
        if (
            run.state.machine_state.status
            is not ExecutionStatus.COMPLETED
        ):
            reasons.append(f"{name}_not_completed")

        if run.effective_result_policy is None:
            reasons.append(f"{name}_unresolved_result_policy")

        if (
            run.state.machine_state.status
            is ExecutionStatus.COMPLETED
            and run.state.canonical_result is None
        ):
            reasons.append(f"{name}_missing_result")

    # Equal workload and observation demand should yield
    # equivalent canonical results across strategies.
    if (
        left.workload_id == right.workload_id
        and left.effective_result_policy is not None
        and left.effective_result_policy
            == right.effective_result_policy
        and left.state.canonical_result is not None
        and right.state.canonical_result is not None
        and left.state.canonical_result
            != right.state.canonical_result
    ):
        reasons.append("different_observable_result")

    return ComparabilityAssessment(
        complete_costs_comparable=not reasons,
        reasons=tuple(reasons),
    )
