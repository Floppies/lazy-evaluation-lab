
from dataclasses import replace

import pytest

from lazy_lab.engine.core_machine import (
    create_initial_core_state,
    run_batch,
)
from lazy_lab.engine.session_runner import run_session_batch
from lazy_lab.metrics.comparison import ComparisonRun, assess_comparability, compare_metric
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


def completed_run(
    strategy=Strategy.CBNEED,
    *,
    source="main = 42",
    workload_id="constant-42",
    policy=ResultPolicy.WHNF_ONLY,
):
    config = replace(
        make_config(policy),
        strategy=strategy,
    )

    initial = create_initial_core_state(
        compile_source(source),
        config,
        session_id="comparison-test",
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

    return ComparisonRun(
        workload_id=workload_id,
        config=config,
        state=completed,
    )


def test_strategy_comparison_requires_declared_factor():
    cbv = completed_run(Strategy.CBV)
    need = completed_run(Strategy.CBNEED)

    undeclared = assess_comparability(cbv, need)

    assert not undeclared.complete_costs_comparable
    assert "different_strategy" in undeclared.reasons

    declared = assess_comparability(
        cbv,
        need,
        varied_factors=frozenset({"strategy"}),
    )

    assert declared.complete_costs_comparable
    assert declared.reasons == ()


def test_result_policy_difference_requires_declaration():
    whnf = completed_run()
    materialized = completed_run(
        policy=ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
    )

    rejected = assess_comparability(whnf, materialized)

    assert not rejected.complete_costs_comparable
    assert "different_result_policy" in rejected.reasons

    allowed = assess_comparability(
        whnf,
        materialized,
        varied_factors=frozenset({"result_policy"}),
    )

    assert allowed.complete_costs_comparable


def test_incomplete_run_is_not_complete_cost_comparable():
    completed = completed_run()

    config = make_config()
    initial = create_initial_core_state(
        compile_source("main = 42"),
        config,
        session_id="comparison-incomplete",
    )

    incomplete = ComparisonRun(
        workload_id="constant-42",
        config=config,
        state=initial,
    )

    assessment = assess_comparability(completed, incomplete)

    assert not assessment.complete_costs_comparable
    assert "right_not_completed" in assessment.reasons


def test_mismatched_observable_results_are_rejected():
    first = completed_run(source="main = 42")
    second = completed_run(source="main = 99")

    assessment = assess_comparability(first, second)

    assert not assessment.complete_costs_comparable
    assert "different_observable_result" in assessment.reasons


def test_complete_metric_comparison_returns_delta_and_ratio():
    cbv = completed_run(Strategy.CBV)
    need = completed_run(Strategy.CBNEED)

    result = compare_metric(
        cbv,
        need,
        "evaluator_transitions",
        varied_factors=frozenset({"strategy"}),
    )

    left = cbv.counters.evaluator_transitions
    right = need.counters.evaluator_transitions

    assert result.left_value == left
    assert result.right_value == right
    assert result.delta == left - right
    assert result.ratio == pytest.approx(left / right)
    assert result.assessment.complete_costs_comparable


def test_zero_denominator_does_not_produce_ratio():
    run = completed_run()

    result = compare_metric(
        run,
        run,
        "result_nodes",
    )

    assert result.left_value == 0
    assert result.right_value == 0
    assert result.delta == 0
    assert result.ratio is None
    assert result.assessment.complete_costs_comparable


def test_incomplete_comparison_has_no_ratio():
    completed = completed_run()

    config = make_config()
    initial = create_initial_core_state(
        compile_source("main = 42"),
        config,
        session_id="incomplete-metric",
    )

    incomplete = ComparisonRun(
        workload_id="constant-42",
        config=config,
        state=initial,
    )

    result = compare_metric(
        completed,
        incomplete,
        "evaluator_transitions",
    )

    assert result.left_value > 0
    assert result.right_value == 0
    assert result.delta == result.left_value
    assert result.ratio is None
    assert not result.assessment.complete_costs_comparable


def test_cbneed_metric_rejects_cross_strategy_comparison():
    cbv = completed_run(Strategy.CBV)
    need = completed_run(Strategy.CBNEED)

    with pytest.raises(
        ValueError,
        match="only applicable to CBNeed",
    ):
        compare_metric(
            cbv,
            need,
            "shared_result_hits",
            varied_factors=frozenset({"strategy"}),
        )


def test_derived_semantic_reductions_are_supported():
    run = completed_run()

    result = compare_metric(
        run,
        run,
        "semantic_reductions",
    )

    assert result.left_value == run.counters.semantic_reductions
    assert result.delta == 0
