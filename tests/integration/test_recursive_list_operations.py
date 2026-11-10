
"""B06.9: Recursive operations on finite lists."""

import pytest

from lazy_lab.engine.core_machine import create_initial_core_state
from lazy_lab.engine.session_runner import run_session_batch
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.observation import (
    CanonicalConstructor,
    CanonicalInteger,
)
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionPhase,
    ExecutionStatus,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.runtime.transitions import BatchStopReason, RuleId


MAP_DEFINITION = """
map f [] = []
map f (h:t) = f h : map f t
double x = x * 2
"""

TAKE_DEFINITION = """
take n xs = if n <= 0 then [] else takePositive n xs
takePositive n [] = []
takePositive n (h:t) = h : take (n - 1) t
"""


def make_config(strategy: Strategy) -> ExecutionConfig:
    return ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=strategy,
        result_policy=ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
        execution_step_limit=3000,
        result_node_limit=100,
        trace_mode=TraceMode.FULL,
    )


def canonical_integer_list(values: tuple[int, ...]):
    result = CanonicalConstructor("Nil", ())

    for value in reversed(values):
        result = CanonicalConstructor(
            "Cons",
            (CanonicalInteger(value), result),
        )

    return result


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
@pytest.mark.parametrize(
    "source_list, expected",
    [
        ("[]", ()),
        ("[1, 2, 3]", (2, 4, 6)),
    ],
)
def test_recursive_map_materializes_finite_list(
    strategy,
    source_list,
    expected,
):
    config = make_config(strategy)

    source = (
        MAP_DEFINITION
        + f"main = map double {source_list}"
    )

    initial = create_initial_core_state(
        compile_source(source),
        config,
        session_id="recursive-map",
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


    if strategy is Strategy.CBNEED and expected:
        local_initializations = [
            entry
            for entry in batch.trace
            if entry.rule_id in (
                RuleId.CORE_LETREC_INSTALL_THUNK,
                RuleId.CORE_LETREC_INSTALL_FUNCTION,
            )
            and entry.phase_before
            is ExecutionPhase.RESULT_MATERIALIZATION
        ]

        assert local_initializations
        assert all(
            entry.phase_after
            is ExecutionPhase.RESULT_MATERIALIZATION
            for entry in local_initializations
        )


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
@pytest.mark.parametrize(
    "count, source_list, expected",
    [
        ("0", "[1, 2, 3]", ()),
        ("(-2)", "[1, 2, 3]", ()),
        ("2", "[]", ()),
        ("2", "[1, 2, 3]", (1, 2)),
        ("5", "[1, 2]", (1, 2)),
        ("3", "[1, 2, 3]", (1, 2, 3)),
    ],
)
def test_recursive_take_materializes_finite_prefix(
    strategy,
    count,
    source_list,
    expected,
):
    config = make_config(strategy)

    source = (
        TAKE_DEFINITION
        + f"main = take {count} {source_list}"
    )

    initial = create_initial_core_state(
        compile_source(source),
        config,
        session_id="recursive-take",
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
