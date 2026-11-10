import pytest

from lazy_lab.engine.core_machine import create_initial_core_state
from lazy_lab.engine.session_runner import run_session_batch
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


FOLDR_DEFINITION = """
foldr f z [] = z
foldr f z (h:t) = f h (foldr f z t)
"""

FOLDL_DEFINITION = """
foldl f z [] = z
foldl f z (h:t) = foldl f (f z h) t
"""

FOLDL_STRICT_DEFINITION = """
foldlStrict f z [] = z
foldlStrict f z (h:t) = let { z1 = f z h } in seq z1 (foldlStrict f z1 t)
"""

ADD_DEFINITION = """
add a b = a + b
"""

IGNORE_DEFINITION = """
ignore a b = a
"""

LAST_VALUE_DEFINITION = """
lastValue acc x = x
"""


def make_config(strategy: Strategy) -> ExecutionConfig:
    return ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=strategy,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=3000,
        result_node_limit=100,
        trace_mode=TraceMode.FULL,
    )


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
@pytest.mark.parametrize(
    "source_list, expected",
    [
        ("[]", 0),
        ("[1, 2, 3]", 6),
    ],
)
def test_foldr_sum_finite_list(
    strategy,
    source_list,
    expected,
):
    config = make_config(strategy)

    source = (
        FOLDR_DEFINITION
        + ADD_DEFINITION
        + f"main = foldr add 0 {source_list}"
    )

    initial = create_initial_core_state(
        compile_source(source),
        config,
        session_id="foldr-sum",
    )

    batch = run_session_batch(
        initial,
        config,
        max_steps=4000,
    )

    assert batch.stop_reason is BatchStopReason.TERMINAL_STATUS
    assert batch.state.machine_state.status is ExecutionStatus.COMPLETED

    assert batch.state.canonical_result == CanonicalInteger(expected)
    assert batch.state.machine_state.stack.depth == 0


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
def test_foldr_short_circuits_unused_tail(strategy):
    config = make_config(strategy)

    source = (
        FOLDR_DEFINITION
        + IGNORE_DEFINITION
        + "main = foldr ignore 0 [1, 1 + True]"
    )

    initial = create_initial_core_state(
        compile_source(source),
        config,
        session_id="foldr-short-circuit",
    )

    if strategy is Strategy.CBV:
        with pytest.raises(
            TypeError,
            match="requires integer operands",
        ):
            run_session_batch(
                initial,
                config,
                max_steps=4000,
            )
    else:
        batch = run_session_batch(
            initial,
            config,
            max_steps=4000,
        )

        assert batch.stop_reason is BatchStopReason.TERMINAL_STATUS
        assert batch.state.machine_state.status is ExecutionStatus.COMPLETED
        assert batch.state.canonical_result == CanonicalInteger(1)


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
@pytest.mark.parametrize(
    "source_list, expected",
    [
        ("[]", 0),
        ("[1]", 1),
        ("[1, 2, 3]", 6),
    ],
)
def test_foldl_sum_finite_list(
    strategy,
    source_list,
    expected,
):
    config = make_config(strategy)

    source = (
        FOLDL_DEFINITION
        + ADD_DEFINITION
        + f"main = foldl add 0 {source_list}"
    )

    initial = create_initial_core_state(
        compile_source(source),
        config,
        session_id="foldl-sum",
    )

    batch = run_session_batch(
        initial,
        config,
        max_steps=4000,
    )

    assert batch.stop_reason is BatchStopReason.TERMINAL_STATUS
    assert batch.state.machine_state.status is ExecutionStatus.COMPLETED

    assert batch.state.canonical_result == CanonicalInteger(expected)
    assert batch.state.machine_state.stack.depth == 0


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
def test_foldl_can_discard_deferred_accumulator(strategy):
    config = make_config(strategy)

    source = (
        FOLDL_DEFINITION
        + LAST_VALUE_DEFINITION
        + "main = foldl lastValue 0 [1 + True, 2]"
    )

    initial = create_initial_core_state(
        compile_source(source),
        config,
        session_id="foldl-deferred-accumulator",
    )

    if strategy is Strategy.CBV:
        with pytest.raises(
            TypeError,
            match="requires integer operands",
        ):
            run_session_batch(
                initial,
                config,
                max_steps=4000,
            )

    else:
        batch = run_session_batch(
            initial,
            config,
            max_steps=4000,
        )

        assert batch.stop_reason is BatchStopReason.TERMINAL_STATUS
        assert batch.state.machine_state.status is ExecutionStatus.COMPLETED
        assert batch.state.canonical_result == CanonicalInteger(2)


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
@pytest.mark.parametrize(
    "source_list, expected",
    [
        ("[]", 0),
        ("[1]", 1),
        ("[1, 2, 3]", 6),
    ],
)
def test_foldl_strict_sum_finite_list(
    strategy,
    source_list,
    expected,
):
    config = make_config(strategy)

    source = (
        FOLDL_STRICT_DEFINITION
        + ADD_DEFINITION
        + f"main = foldlStrict add 0 {source_list}"
    )

    initial = create_initial_core_state(
        compile_source(source),
        config,
        session_id="foldl-strict-sum",
    )

    batch = run_session_batch(
        initial,
        config,
        max_steps=4000,
    )

    assert batch.stop_reason is BatchStopReason.TERMINAL_STATUS
    assert batch.state.machine_state.status is ExecutionStatus.COMPLETED

    assert batch.state.canonical_result == CanonicalInteger(expected)
    assert batch.state.machine_state.stack.depth == 0


def test_foldl_strict_forces_intermediate_accumulator_cbneed():
    config = make_config(Strategy.CBNEED)

    source = (
        FOLDL_STRICT_DEFINITION
        + LAST_VALUE_DEFINITION
        + "main = foldlStrict lastValue 0 [1 + True, 2]"
    )

    initial = create_initial_core_state(
        compile_source(source),
        config,
        session_id="foldl-strict-demand",
    )

    with pytest.raises(
        TypeError,
        match="requires integer operands",
    ):
        run_session_batch(
            initial,
            config,
            max_steps=4000,
        )
