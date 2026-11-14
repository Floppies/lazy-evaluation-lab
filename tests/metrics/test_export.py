
import csv
from dataclasses import fields, replace
from io import StringIO
import json

import pytest

from lazy_lab.engine.core_machine import (
    create_initial_core_state,
    run_batch,
)
from lazy_lab.engine.session_runner import run_session_batch
from lazy_lab.metrics.comparison import ComparisonRun
from lazy_lab.metrics.export import (
    RUN_RECORD_SCHEMA_VERSION,
    RunRecord,
    build_run_record,
    run_records_to_csv,
)
from lazy_lab.metrics.state import InstrumentationState, MetricCounters
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.observation import CanonicalBoolean, CanonicalConstructor, CanonicalInteger, ConstructorWHNF, OpaqueFunction
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionStatus,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.runtime.transitions import BatchStopReason
from lazy_lab.metrics.export import (
    run_record_to_dict,
    run_record_to_json,
)


def make_config():
    return ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=100,
        result_node_limit=50,
        trace_mode=TraceMode.FULL,
    )


def test_complete_run_record_preserves_measurement():
    config = make_config()

    initial = create_initial_core_state(
        compile_source("main = 42"),
        config,
        session_id="export-completed",
    )

    completed = run_session_batch(
        initial,
        config,
        max_steps=100,
    ).state

    run = ComparisonRun(
        workload_id="constant-42",
        config=config,
        state=completed,
    )

    record = build_run_record(run)

    assert record.schema_version == RUN_RECORD_SCHEMA_VERSION
    assert record.workload_id == "constant-42"
    assert record.session_id == "export-completed"
    assert record.config == config
    assert record.status is ExecutionStatus.COMPLETED
    assert record.canonical_result == CanonicalInteger(42)
    assert record.effective_result_policy is ResultPolicy.WHNF_ONLY
    assert record.stop_reason is None
    assert record.is_complete

    assert record.instrumentation == completed.instrumentation_state
    assert record.transition_index == completed.transition_index


def test_budget_limited_run_record_preserves_stop_reason():
    config = replace(
        make_config(),
        execution_step_limit=2,
    )

    initial = create_initial_core_state(
        compile_source("main = 1 + 2"),
        config,
        session_id="export-budget",
    )

    batch = run_batch(
        initial,
        config,
        max_steps=100,
    )

    assert batch.stop_reason is BatchStopReason.EVALUATOR_BUDGET

    run = ComparisonRun(
        workload_id="addition",
        config=config,
        state=batch.state,
    )

    record = build_run_record(
        run,
        stop_reason=batch.stop_reason,
    )

    assert record.status is ExecutionStatus.RUNNING
    assert record.stop_reason is BatchStopReason.EVALUATOR_BUDGET
    assert record.canonical_result is None
    assert not record.is_complete

    assert record.instrumentation == (
        batch.state.instrumentation_state
    )


def test_partial_canonical_result_json_encoding():
    from lazy_lab.metrics.export import RunRecord
    from lazy_lab.metrics.state import InstrumentationState
    from lazy_lab.runtime.observation import (
        CanonicalInteger,
        CanonicalPending,
        CanonicalPartialConstructor,
    )

    record = RunRecord(
        workload_id="partial-list",
        session_id="partial-export",
        transition_index=10,
        config=make_config(),
        effective_result_policy=ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
        status=ExecutionStatus.RESULT_LIMIT_REACHED,
        stop_reason=BatchStopReason.TERMINAL_STATUS,
        canonical_result=CanonicalPartialConstructor(
            "Cons",
            (
                CanonicalInteger(1),
                CanonicalPending(),
            ),
            unvisited_fields=0,
        ),
        instrumentation=InstrumentationState(),
    )

    result = run_record_to_dict(record)

    assert result["canonical_result"] == {
        "kind": "partial_constructor",
        "tag": "Cons",
        "fields": [
            {"kind": "integer", "value": 1},
            {"kind": "pending"},
        ],
        "unvisited_fields": 0,
    }

    assert result["status"] == "RESULT_LIMIT_REACHED"
    assert json.loads(run_record_to_json(record)) == result


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (CanonicalBoolean(True), {"kind": "boolean", "value": True}),
        (OpaqueFunction(), {"kind": "opaque_function"}),
        (
            ConstructorWHNF("Cons", 2),
            {"kind": "constructor_whnf", "tag": "Cons", "arity": 2},
        ),
        (
            CanonicalConstructor("Nil", ()),
            {"kind": "constructor", "tag": "Nil", "fields": []},
        ),
    ],
)
def test_remaining_canonical_json_variants(value, expected):
    record = RunRecord(
        workload_id="variants",
        session_id="variants-export",
        transition_index=1,
        config=make_config(),
        effective_result_policy=ResultPolicy.WHNF_ONLY,
        status=ExecutionStatus.COMPLETED,
        stop_reason=None,
        canonical_result=value,
        instrumentation=InstrumentationState(),
    )

    assert run_record_to_dict(record)["canonical_result"] == expected


def test_csv_exports_multiple_runs_with_stable_columns():
    first = RunRecord(
        workload_id="example-01",
        session_id="csv-first",
        transition_index=17,
        config=make_config(),
        effective_result_policy=ResultPolicy.WHNF_ONLY,
        status=ExecutionStatus.COMPLETED,
        stop_reason=None,
        canonical_result=CanonicalInteger(42),
        instrumentation=InstrumentationState(
            counters=MetricCounters(
                evaluator_transitions=16,
                result_consumer_transitions=1,
            ),
            baseline_slots=3,
        ),
    )

    second = replace(
        first,
        session_id="csv,second",
        config=replace(
            first.config,
            strategy=Strategy.CBV,
        ),
        instrumentation=InstrumentationState(
            counters=MetricCounters(
                evaluator_transitions=12,
                result_consumer_transitions=1,
            ),
            baseline_slots=2,
        ),
    )

    output = run_records_to_csv([first, second])

    reader = csv.DictReader(StringIO(output))
    rows = list(reader)

    assert len(rows) == 2

    expected_columns = (
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
    ) + tuple(
        f"metric_{field.name}"
        for field in fields(MetricCounters)
    )

    assert reader.fieldnames == list(expected_columns)

    assert rows[0]["strategy"] == "CBNEED"
    assert rows[1]["strategy"] == "CBV"

    assert rows[0]["metric_evaluator_transitions"] == "16"
    assert rows[1]["metric_evaluator_transitions"] == "12"

    assert rows[0]["baseline_slots"] == "3"
    assert rows[1]["baseline_slots"] == "2"

    # CSV escaping is handled by the standard library.
    assert rows[1]["session_id"] == "csv,second"

    # Optional metadata uses empty cells.
    assert rows[0]["stop_reason"] == ""

    # Canonical trees belong to JSON, not metrics CSV.
    assert "canonical_result" not in reader.fieldnames

    assert output == run_records_to_csv([first, second])


def test_csv_empty_collection_preserves_header():
    output = run_records_to_csv([])

    reader = csv.DictReader(StringIO(output))

    assert list(reader) == []
    assert "metric_evaluator_transitions" in reader.fieldnames
    assert "schema_version" in reader.fieldnames


def test_csv_rejects_invalid_records():
    with pytest.raises(TypeError, match="Expected RunRecord"):
        run_records_to_csv([object()])


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
def test_json_and_csv_preserve_real_execution_metrics(strategy):
    source = "main = [1, 2]"
    program = compile_source(source)

    config = replace(
        make_config(),
        strategy=strategy,
        result_policy=ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
        execution_step_limit=300,
        result_node_limit=50,
    )

    records = []

    for node_limit in (50, 2):
        run_config = replace(
            config,
            result_node_limit=node_limit,
        )

        initial = create_initial_core_state(
            program,
            run_config,
            session_id=f"export-{strategy.value}-{node_limit}",
        )

        batch = run_session_batch(
            initial,
            run_config,
            max_steps=500,
        )

        measured = ComparisonRun(
            workload_id="finite-list",
            config=run_config,
            state=batch.state,
        )

        original_metrics = batch.state.instrumentation_state

        record = build_run_record(
            measured,
            stop_reason=batch.stop_reason,
        )

        assert record.instrumentation == original_metrics
        assert batch.state.instrumentation_state == original_metrics

        records.append(record)

    complete, limited = records

    assert complete.status is ExecutionStatus.COMPLETED
    assert limited.status is ExecutionStatus.RESULT_LIMIT_REACHED

    assert complete.is_complete
    assert not limited.is_complete

    assert complete.instrumentation.counters.result_nodes == 5
    assert limited.instrumentation.counters.result_nodes == 2

    csv_output = run_records_to_csv(records)
    rows = list(csv.DictReader(StringIO(csv_output)))

    assert len(rows) == 2

    for record, row in zip(records, rows):
        document = json.loads(run_record_to_json(record))

        assert document["schema_version"] == record.schema_version
        assert row["schema_version"] == str(record.schema_version)

        assert document["status"] == row["status"]
        assert document["stop_reason"] == row["stop_reason"]

        for metric_name, value in document["instrumentation"][
            "counters"
        ].items():
            assert row[f"metric_{metric_name}"] == str(value)

        baseline = document["instrumentation"]["baseline_slots"]

        assert row["baseline_slots"] == (
            "" if baseline is None else str(baseline)
        )

    assert run_records_to_csv(records) == csv_output
