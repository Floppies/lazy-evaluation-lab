
from dataclasses import replace

import pytest

from lazy_lab.engine.core_machine import create_initial_core_state
from lazy_lab.engine.session_runner import run_session_batch
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.state import ExecutionStatus, Strategy
from lazy_lab.runtime.transitions import BatchStopReason

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
