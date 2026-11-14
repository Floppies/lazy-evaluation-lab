
from dataclasses import replace

import pytest

from lazy_lab.engine.core_machine import (
    create_initial_core_state,
    run_batch,
)
from lazy_lab.engine.session_runner import run_session_batch
from lazy_lab.metrics.comparison import ComparisonRun
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionStatus,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)


def make_config(
    policy=ResultPolicy.WHNF_ONLY,
):
    return ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        result_policy=policy,
        execution_step_limit=100,
        result_node_limit=50,
        trace_mode=TraceMode.FULL,
    )


def test_comparison_run_reads_accumulated_metrics():
    config = make_config()

    initial = create_initial_core_state(
        compile_source("main = 42"),
        config,
        session_id="comparison-run",
    )

    completed = run_session_batch(
        initial,
        config,
        max_steps=100,
    ).state

    assert (
        completed.machine_state.status
        is ExecutionStatus.COMPLETED
    )

    run = ComparisonRun(
        workload_id="constant-42",
        config=config,
        state=completed,
    )

    assert run.counters == (
        completed.instrumentation_state.counters
    )
    assert run.counters.evaluator_transitions > 0
    assert run.effective_result_policy is ResultPolicy.WHNF_ONLY

    assert initial.instrumentation_state.counters.evaluator_transitions == 0


def test_unresolved_interactive_policy_has_no_effective_mode():
    config = make_config(ResultPolicy.ASK_AT_WHNF)

    initial = create_initial_core_state(
        compile_source("main = 42"),
        config,
        session_id="comparison-interactive",
    )

    pending = run_batch(
        initial,
        config,
        max_steps=100,
    ).state

    run = ComparisonRun(
        workload_id="constant-42",
        config=config,
        state=pending,
    )

    assert run.effective_result_policy is None


def test_comparison_run_rejects_mismatched_configuration():
    config = make_config()

    initial = create_initial_core_state(
        compile_source("main = 42"),
        config,
        session_id="comparison-invalid-config",
    )

    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        ComparisonRun(
            workload_id="constant-42",
            config=replace(config, strategy=Strategy.CBV),
            state=initial,
        )
