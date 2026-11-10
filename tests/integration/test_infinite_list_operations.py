
from dataclasses import replace

import pytest

from lazy_lab.engine.core_machine import create_initial_core_state
from lazy_lab.engine.session_runner import run_session_batch
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.observation import CanonicalInteger, CanonicalPartialConstructor, CanonicalPending
from lazy_lab.runtime.state import ExecutionPhase, ExecutionStatus, Strategy
from lazy_lab.runtime.transitions import BatchStopReason

from tests.helpers.runtime_equivalence import runtime_fingerprint
from tests.integration.test_recursive_list_operations import (
    MAP_DEFINITION,
    TAKE_DEFINITION,
    canonical_integer_list,
    make_config,
)


FROM_DEFINITION = """
from n = n : from (n + 1)
"""


@pytest.mark.parametrize(
    "expression, expected, needs_map",
    [
        (
            "take 5 (from 1)",
            (1, 2, 3, 4, 5),
            False,
        ),
        (
            "take 4 (map double (from 1))",
            (2, 4, 6, 8),
            True,
        ),
    ],
)
def test_cbneed_consumes_finite_prefix_of_infinite_list(
    expression,
    expected,
    needs_map,
):
    config = make_config(Strategy.CBNEED)

    source = (
        FROM_DEFINITION
        + TAKE_DEFINITION
        + (MAP_DEFINITION if needs_map else "")
        + f"main = {expression}"
    )

    initial = create_initial_core_state(
        compile_source(source),
        config,
        session_id="infinite-list-prefix",
    )

    batch = run_session_batch(
        initial,
        config,
        max_steps=4000,
    )

    assert batch.stop_reason is BatchStopReason.TERMINAL_STATUS
    assert batch.state.machine_state.status is ExecutionStatus.COMPLETED

    assert batch.state.canonical_result == canonical_integer_list(
        expected
    )

    assert batch.state.machine_state.stack.depth == 0


@pytest.mark.parametrize(
    "expression, needs_map",
    [
        ("take 5 (from 1)", False),
        ("take 4 (map double (from 1))", True),
    ],
)
def test_cbv_infinite_list_reaches_evaluator_budget(
    expression,
    needs_map,
):
    config = replace(
        make_config(Strategy.CBV),
        execution_step_limit=150,
    )

    source = (
        FROM_DEFINITION
        + TAKE_DEFINITION
        + (MAP_DEFINITION if needs_map else "")
        + f"main = {expression}"
    )

    initial = create_initial_core_state(
        compile_source(source),
        config,
        session_id="cbv-infinite-list-budget",
    )

    batch = run_session_batch(
        initial,
        config,
        max_steps=500,
    )

    assert batch.stop_reason is BatchStopReason.EVALUATOR_BUDGET

    machine = batch.state.machine_state

    assert machine.status is ExecutionStatus.RUNNING
    assert (
        machine.evaluator_transition_count
        == config.execution_step_limit
    )

    assert batch.state.canonical_result is None

    # The exhausted evaluator cannot execute another transition.
    repeated = run_session_batch(
        batch.state,
        config,
        max_steps=10,
    )

    assert repeated.stop_reason is BatchStopReason.EVALUATOR_BUDGET
    assert repeated.state is batch.state
    assert repeated.trace == ()


def test_infinite_list_materialization_stops_at_node_limit():
    config = replace(
        make_config(Strategy.CBNEED),
        result_node_limit=4,
    )

    initial = create_initial_core_state(
        compile_source(
            FROM_DEFINITION + "main = from 1"
        ),
        config,
        session_id="infinite-list-materialization-limit",
    )

    batch = run_session_batch(
        initial,
        config,
        max_steps=4000,
    )

    assert batch.stop_reason is BatchStopReason.TERMINAL_STATUS

    machine = batch.state.machine_state

    assert machine.status is ExecutionStatus.RESULT_LIMIT_REACHED
    assert machine.phase is ExecutionPhase.RESULT_MATERIALIZATION

    expected = CanonicalPartialConstructor(
        "Cons",
        (
            CanonicalInteger(1),
            CanonicalPartialConstructor(
                "Cons",
                (
                    CanonicalInteger(2),
                    CanonicalPending(),
                ),
            ),
        ),
    )

    assert batch.state.canonical_result == expected

    progress = machine.result_state.materialization

    assert progress is not None
    assert progress.limit_reached
    assert progress.visited_nodes == 4

    # The evaluator budget was not exhausted.
    assert (
        machine.evaluator_transition_count
        < config.execution_step_limit
    )


@pytest.mark.parametrize(
    "strategy, expression, evaluator_limit, node_limit, "
    "expected_reason, expected_status",
    [
        (
            Strategy.CBNEED,
            "from 1",
            3000,
            4,
            BatchStopReason.TERMINAL_STATUS,
            ExecutionStatus.RESULT_LIMIT_REACHED,
        ),
        (
            Strategy.CBV,
            "take 5 (from 1)",
            150,
            100,
            BatchStopReason.EVALUATOR_BUDGET,
            ExecutionStatus.RUNNING,
        ),
    ],
)
def test_infinite_list_limits_are_deterministic_across_batches(
    strategy,
    expression,
    evaluator_limit,
    node_limit,
    expected_reason,
    expected_status,
):
    config = replace(
        make_config(strategy),
        execution_step_limit=evaluator_limit,
        result_node_limit=node_limit,
    )

    source = (
        FROM_DEFINITION
        + TAKE_DEFINITION
        + f"main = {expression}"
    )

    initial = create_initial_core_state(
        compile_source(source),
        config,
        session_id="infinite-list-batching",
    )

    # Execute without intermediate batch boundaries.
    uninterrupted = run_session_batch(
        initial,
        config,
        max_steps=4000,
    )

    assert uninterrupted.stop_reason is expected_reason
    assert (
        uninterrupted.state.machine_state.status
        is expected_status
    )

    # Execute the same initial state in small batches.
    current = initial
    combined_trace = []
    batch_count = 0

    for _ in range(4000):
        batch = run_session_batch(
            current,
            config,
            max_steps=3,
        )

        current = batch.state
        combined_trace.extend(batch.trace)
        batch_count += 1

        if batch.stop_reason is BatchStopReason.BATCH_LIMIT:
            continue

        assert batch.stop_reason is expected_reason
        break
    else:
        pytest.fail("Execution did not reach the expected limit")

    assert batch_count > 1
    assert current.machine_state.status is expected_status

    # No differences in heap, stack, references, counters,
    # materialization progress or canonical result.
    assert runtime_fingerprint(current) == runtime_fingerprint(
        uninterrupted.state
    )

    # Batch boundaries must not add or lose transitions.
    assert tuple(combined_trace) == uninterrupted.trace

    if strategy is Strategy.CBNEED:
        progress = current.machine_state.result_state.materialization

        assert progress is not None
        assert progress.limit_reached
        assert progress.visited_nodes == 4

    else:
        assert (
            current.machine_state.evaluator_transition_count
            == evaluator_limit
        )
        assert current.canonical_result is None
