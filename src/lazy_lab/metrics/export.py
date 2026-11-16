
"""Versioned records for exporting measured executions."""

from __future__ import annotations

import csv
from io import StringIO
import json
from dataclasses import dataclass, asdict, fields
from typing import Iterable

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
from lazy_lab.metrics.state import InstrumentationState, MetricCounters
from lazy_lab.runtime.observation import PartialCanonicalValue
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionStatus,
    ResultPolicy,
)
from lazy_lab.runtime.transitions import BatchStopReason


RUN_RECORD_SCHEMA_VERSION = 1

_CSV_METADATA_FIELDS = (
    "schema_version",
    "workload_id",
    "session_id",
    "transition_index",
    "machine_kind",
    "strategy",
    "result_policy",
    "effective_result_policy",
    "execution_step_limit",
    "result_node_limit",
    "trace_mode",
    "status",
    "stop_reason",
    "baseline_slots",
)

_CSV_COUNTER_FIELDS = tuple(
    field.name for field in fields(MetricCounters)
)

_CSV_FIELDS = _CSV_METADATA_FIELDS + tuple(
    f"metric_{name}"
    for name in _CSV_COUNTER_FIELDS
)


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
    """Encode canonical values using an explicit traversal stack."""

    root: list[dict[str, object] | None] = [None]
    pending = [(value, root, 0)]

    while pending:
        current, target, index = pending.pop()

        if current is None:
            encoded = None

        elif isinstance(current, CanonicalInteger):
            encoded = {
                "kind": "integer",
                "value": current.value,
            }

        elif isinstance(current, CanonicalBoolean):
            encoded = {
                "kind": "boolean",
                "value": current.value,
            }

        elif isinstance(current, OpaqueFunction):
            encoded = {"kind": "opaque_function"}

        elif isinstance(current, ConstructorWHNF):
            encoded = {
                "kind": "constructor_whnf",
                "tag": current.tag,
                "arity": current.arity,
            }

        elif isinstance(current, CanonicalPending):
            encoded = {"kind": "pending"}

        elif isinstance(
            current,
            (CanonicalConstructor, CanonicalPartialConstructor),
        ):
            children = [None] * len(current.fields)

            encoded = {
                "kind": (
                    "partial_constructor"
                    if isinstance(current, CanonicalPartialConstructor)
                    else "constructor"
                ),
                "tag": current.tag,
                "fields": children,
            }

            if isinstance(current, CanonicalPartialConstructor):
                encoded["unvisited_fields"] = current.unvisited_fields

            for child_index in range(len(current.fields) - 1, -1, -1):
                pending.append((
                    current.fields[child_index],
                    children,
                    child_index,
                ))

        else:
            raise TypeError(
                f"Unsupported canonical result: {type(current).__name__}"
            )

        target[index] = encoded

    return root[0]

def _json_dumps_iterative(value: object) -> str:
    """Encode JSON-compatible data without recursive container traversal."""

    output = StringIO()
    pending = [("value", value)]

    while pending:
        operation, item = pending.pop()

        if operation == "text":
            output.write(item)
            continue

        if isinstance(item, dict):
            output.write("{")
            pairs = sorted(item.items())
            pending.append(("text", "}"))

            for i in range(len(pairs) - 1, -1, -1):
                key, child = pairs[i]

                if i < len(pairs) - 1:
                    pending.append(("text", ","))

                pending.append(("value", child))
                pending.append(("text", ":"))
                pending.append((
                    "text",
                    json.dumps(key, ensure_ascii=False),
                ))

            continue

        if isinstance(item, list):
            output.write("[")
            pending.append(("text", "]"))

            for i in range(len(item) - 1, -1, -1):
                if i < len(item) - 1:
                    pending.append(("text", ","))

                pending.append(("value", item[i]))

            continue

        # Standard library handles escaping and scalar types.
        output.write(
            json.dumps(
                item,
                ensure_ascii=False,
                allow_nan=False,
            )
        )

    return output.getvalue()

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

    return _json_dumps_iterative(
        run_record_to_dict(record)
    )

def run_records_to_csv(
    records: Iterable[RunRecord],
) -> str:
    """Serialize measured runs to a deterministic CSV table."""

    output = StringIO(newline="")

    writer = csv.DictWriter(
        output,
        fieldnames=_CSV_FIELDS,
        lineterminator="\n",
    )
    writer.writeheader()

    for record in records:
        if not isinstance(record, RunRecord):
            raise TypeError("Expected RunRecord")

        config = record.config

        row = {
            "schema_version": record.schema_version,
            "workload_id": record.workload_id,
            "session_id": record.session_id,
            "transition_index": record.transition_index,
            "machine_kind": config.machine_kind.value,
            "strategy": config.strategy.value,
            "result_policy": config.result_policy.value,
            "effective_result_policy": (
                record.effective_result_policy.value
                if record.effective_result_policy is not None
                else None
            ),
            "execution_step_limit": config.execution_step_limit,
            "result_node_limit": config.result_node_limit,
            "trace_mode": config.trace_mode.value,
            "status": record.status.value,
            "stop_reason": (
                record.stop_reason.value
                if record.stop_reason is not None
                else None
            ),
            "baseline_slots": (
                record.instrumentation.baseline_slots
            ),
        }

        counters = record.instrumentation.counters

        row.update({
            f"metric_{name}": getattr(counters, name)
            for name in _CSV_COUNTER_FIELDS
        })

        writer.writerow(row)

    return output.getvalue()
