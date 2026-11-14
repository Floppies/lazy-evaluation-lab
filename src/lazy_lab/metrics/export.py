
"""Versioned records for exporting measured executions."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict

from lazy_lab.runtime.observation import (
    CanonicalInteger,
    CanonicalBoolean,
    CanonicalConstructor,
    CanonicalPartialConstructor,
    ConstructorWHNF,
    CanonicalPending,
    OpaqueFunction,
)
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

def _canonical_to_data(
    value: PartialCanonicalValue | None,
) -> dict[str, object] | None:
    """Encode canonical values without runtime references."""

    if value is None:
        return None

    if isinstance(value, CanonicalInteger):
        return {
            "kind": "integer",
            "value": value.value,
        }

    if isinstance(value, CanonicalBoolean):
        return {
            "kind": "boolean",
            "value": value.value,
        }

    if isinstance(value, OpaqueFunction):
        return {"kind": "opaque_function"}

    if isinstance(value, ConstructorWHNF):
        return {
            "kind": "constructor_whnf",
            "tag": value.tag,
            "arity": value.arity,
        }

    if isinstance(value, CanonicalPending):
        return {"kind": "pending"}

    if isinstance(value, CanonicalPartialConstructor):
        return {
            "kind": "partial_constructor",
            "tag": value.tag,
            "fields": [
                _canonical_to_data(field)
                for field in value.fields
            ],
            "unvisited_fields": value.unvisited_fields,
        }

    if isinstance(value, CanonicalConstructor):
        return {
            "kind": "constructor",
            "tag": value.tag,
            "fields": [
                _canonical_to_data(field)
                for field in value.fields
            ],
        }

    raise TypeError(
        f"Unsupported canonical result: {type(value).__name__}"
    )


def run_record_to_dict(record: RunRecord) -> dict[str, object]:
    """Convert a run record into JSON-compatible values."""

    if not isinstance(record, RunRecord):
        raise TypeError("Expected RunRecord")

    config = record.config
    instrumentation = record.instrumentation

    return {
        "schema_version": record.schema_version,
        "workload_id": record.workload_id,
        "session_id": record.session_id,
        "transition_index": record.transition_index,
        "config": {
            "machine_kind": config.machine_kind.value,
            "strategy": config.strategy.value,
            "result_policy": config.result_policy.value,
            "execution_step_limit": config.execution_step_limit,
            "result_node_limit": config.result_node_limit,
            "trace_mode": config.trace_mode.value,
        },
        "effective_result_policy": (
            record.effective_result_policy.value
            if record.effective_result_policy is not None
            else None
        ),
        "status": record.status.value,
        "stop_reason": (
            record.stop_reason.value
            if record.stop_reason is not None
            else None
        ),
        "canonical_result": _canonical_to_data(
            record.canonical_result
        ),
        "instrumentation": {
            "counters": asdict(instrumentation.counters),
            "baseline_slots": instrumentation.baseline_slots,
        },
    }


def run_record_to_json(record: RunRecord) -> str:
    """Serialize one run record to deterministic JSON."""

    return json.dumps(
        run_record_to_dict(record),
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    )
