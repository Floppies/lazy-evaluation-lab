
"""B02-to-B03 integration tests for the limited Core runtime."""

from dataclasses import replace

import pytest

from lazy_lab.pipeline import compile_source
from lazy_lab.engine.core_machine import (
    UnsupportedTransitionError,
    run_batch,
    step,
)
from lazy_lab.runtime.control import EvaluateCore, Return
from lazy_lab.runtime.environment import Environment
from lazy_lab.runtime.heap import Heap, Indirection, Reserved
from lazy_lab.runtime.references import (
    ImmediateBoolean,
    ImmediateInteger,
)
from lazy_lab.runtime.stack import Stack
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionPhase,
    ExecutionState,
    ExecutionStatus,
    MachineKind,
    MachineState,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.runtime.transitions import BatchStopReason


def make_config(
    strategy: Strategy = Strategy.CBNEED,
    trace_mode: TraceMode = TraceMode.FULL,
) -> ExecutionConfig:
    return ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=strategy,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=100,
        result_node_limit=100,
        trace_mode=trace_mode,
    )


def make_demo_state(
    source: str,
    strategy: Strategy = Strategy.CBNEED,
) -> ExecutionState:
    program = compile_source(source)

    entry = next(
        (binding for binding in program.bindings
         if binding.name == "main"),
        None,
    )

    if entry is None:
        raise ValueError("Test program must define main")

    # Temporary test boundary: global bindings are NOT initialized.
    environment = Environment()

    machine = MachineState(
        machine_kind=MachineKind.CORE,
        strategy=strategy,
        status=ExecutionStatus.RUNNING,
        phase=ExecutionPhase.EVALUATION,
        control=EvaluateCore(entry.rhs),
        local_environment=environment,
        global_environment=environment,
        heap=Heap(),
        stack=Stack(),
    )

    return ExecutionState(
        state_id=0,
        session_id="b03-integration-test",
        transition_index=0,
        machine_state=machine,
    )


@pytest.mark.parametrize(
    "source,expected_reference,expected_rule",
    [
        (
            "main = 42",
            ImmediateInteger(42),
            "CORE_EVAL_INTEGER",
        ),
        (
            "main = True",
            ImmediateBoolean(True),
            "CORE_EVAL_BOOLEAN",
        ),
        (
            "unused = 7\nmain = False",
            ImmediateBoolean(False),
            "CORE_EVAL_BOOLEAN",
        ),
    ],
)
@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBN, Strategy.CBNEED],
)
def test_compiled_literals_use_runtime(
    source,
    expected_reference,
    expected_rule,
    strategy,
):
    state = make_demo_state(source, strategy)
    config = make_config(strategy)

    result = run_batch(state, config, max_steps=10)
    next_state = result.state

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    assert next_state.machine_state.control == Return(
        expected_reference
    )
    assert next_state.machine_state.status is ExecutionStatus.RUNNING

    assert next_state.transition_index == 1
    assert next_state.machine_state.evaluator_transition_count == 1

    assert next_state.machine_state.heap.current_slots == 0
    assert next_state.machine_state.stack.depth == 0

    assert len(result.trace) == 1
    assert result.trace[0].rule_id == expected_rule
    assert result.trace[0].previous_state_id == 0
    assert result.trace[0].next_state_id == 1

#TODO these tests are temporary
@pytest.mark.parametrize(
    "source",
    [
        "main = 1 + 2",
        "x = 42\nmain = x",
        "main = let { x = 1 } in x",
    ],
)
def test_unimplemented_core_constructs_remain_unsupported(source):
    state = make_demo_state(source)

    with pytest.raises(UnsupportedTransitionError):
        step(state, make_config())

    assert state.state_id == 0
    assert state.transition_index == 0
    assert state.machine_state.evaluator_transition_count == 0

def test_trace_mode_does_not_change_semantic_result():
    state = make_demo_state("main = True")

    full = run_batch(
        state,
        make_config(trace_mode=TraceMode.FULL),
        max_steps=10,
    )

    metrics_only = run_batch(
        state,
        make_config(trace_mode=TraceMode.METRICS_ONLY),
        max_steps=10,
    )

    assert (
        full.state.machine_state.control
        == metrics_only.state.machine_state.control
    )

    assert (
        full.state.machine_state.evaluator_transition_count
        == metrics_only.state.machine_state.evaluator_transition_count
    )

    assert full.state.transition_index == metrics_only.state.transition_index

    assert len(full.trace) == 1
    assert metrics_only.trace == ()
