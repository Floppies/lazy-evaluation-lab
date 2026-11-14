
"""Comparison context for completed or partial metric runs."""

from __future__ import annotations

from dataclasses import dataclass

from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionState,
    ResultPolicy,
)
from lazy_lab.metrics.state import MetricCounters


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
