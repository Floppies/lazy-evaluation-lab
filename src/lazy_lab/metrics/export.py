
"""Versioned records for exporting measured executions."""

from __future__ import annotations

from dataclasses import dataclass

from lazy_lab.metrics.comparison import ComparisonRun
from lazy_lab.metrics.state import InstrumentationState
from lazy_lab.runtime.observation import PartialCanonicalValue
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionStatus,
    ResultPolicy,
)
from lazy_lab.runtime.transitions import BatchStopReason


RUN_RECORD_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class RunRecord:
    """Immutable measurement data for one execution."""

    workload_id: str
    session_id: str
    transition_index: int
    config: ExecutionConfig
    effective_result_policy: ResultPolicy | None
    status: ExecutionStatus
    stop_reason: BatchStopReason | None
    canonical_result: PartialCanonicalValue | None
    instrumentation: InstrumentationState
    schema_version: int = RUN_RECORD_SCHEMA_VERSION

    @property
    def is_complete(self) -> bool:
        """Whether a complete canonical result is available."""
        return (
            self.status is ExecutionStatus.COMPLETED
            and self.canonical_result is not None
        )


def build_run_record(
    run: ComparisonRun,
    *,
    stop_reason: BatchStopReason | None = None,
) -> RunRecord:
    """Capture the exportable data of a measured execution."""

    if not isinstance(run, ComparisonRun):
        raise TypeError("Expected ComparisonRun")

    if (
        stop_reason is not None
        and not isinstance(stop_reason, BatchStopReason)
    ):
        raise TypeError("Expected BatchStopReason or None")

    state = run.state

    return RunRecord(
        workload_id=run.workload_id,
        session_id=state.session_id,
        transition_index=state.transition_index,
        config=run.config,
        effective_result_policy=run.effective_result_policy,
        status=state.machine_state.status,
        stop_reason=stop_reason,
        canonical_result=state.canonical_result,
        instrumentation=state.instrumentation_state,
    )
