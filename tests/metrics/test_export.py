
from dataclasses import replace

from lazy_lab.engine.core_machine import (
    create_initial_core_state,
    run_batch,
)
from lazy_lab.engine.session_runner import run_session_batch
from lazy_lab.metrics.comparison import ComparisonRun
from lazy_lab.metrics.export import (
    RUN_RECORD_SCHEMA_VERSION,
    build_run_record,
)
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.observation import CanonicalInteger
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionStatus,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.runtime.transitions import BatchStopReason


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
