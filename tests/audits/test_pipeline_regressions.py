"""Real compilation to literal stepping, without recursive global initialization."""

import pytest

from lazy_lab.core.nodes import CoreInt
from lazy_lab.engine.core_machine import UnsupportedTransitionError, run_batch, step
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.control import EvaluateCore, Return
from lazy_lab.runtime.environment import Environment
from lazy_lab.runtime.heap import Heap
from lazy_lab.runtime.references import ImmediateBoolean, ImmediateInteger
from lazy_lab.runtime.stack import Stack, PrimitiveOperandsFrame
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
from lazy_lab.semantics.name_resolution import NameResolutionError


def literal_demo(expression, strategy, trace_mode):
    # This extracts an already selected RHS; it does not initialize globals.
    environment = Environment()
    state = ExecutionState(
        state_id=0,
        session_id="compiled-b03-audit",
        transition_index=0,
        machine_state=MachineState(
            machine_kind=MachineKind.CORE,
            strategy=strategy,
            status=ExecutionStatus.RUNNING,
            phase=ExecutionPhase.EVALUATION,
            control=EvaluateCore(expression),
            local_environment=environment,
            global_environment=environment,
            heap=Heap(),
            stack=Stack(),
        ),
    )
    config = ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=strategy,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=1,
        result_node_limit=1,
        trace_mode=trace_mode,
    )
    return state, config


@pytest.mark.parametrize("strategy", list(Strategy))
@pytest.mark.parametrize("trace_mode", list(TraceMode))
@pytest.mark.parametrize("literal", ["0", str(10**100), "True", "False"])
def test_compiled_main_literal_with_globals_before_and_after(literal, strategy, trace_mode):
    program = compile_source(f"before = after\nmain = {literal}\nafter = before")
    assert tuple(binding.name for binding in program.bindings) == ("before", "main", "after")
    expression = next(binding.rhs for binding in program.bindings if binding.name == "main")
    state, config = literal_demo(expression, strategy, trace_mode)
    result = run_batch(state, config, max_steps=5)
    machine = result.state.machine_state
    assert isinstance(machine.control, Return)
    reference = machine.control.reference
    expected_type = ImmediateInteger if isinstance(expression, CoreInt) else ImmediateBoolean
    assert type(reference) is expected_type
    assert reference.value is expression.value
    assert machine.heap.current_slots == machine.next_object_id == 0
    assert machine.stack.depth == 0
    assert machine.local_environment.bindings == {}
    assert machine.global_environment.bindings == {}
    assert machine.evaluator_transition_count == result.state.transition_index == 1
    assert machine.status is ExecutionStatus.RUNNING
    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert len(result.trace) == (0 if trace_mode is TraceMode.METRICS_ONLY else 1)
    assert state.machine_state.control.expression is expression
    assert state.machine_state.evaluator_transition_count == state.transition_index == 0
    assert state.machine_state.heap is not machine.heap
    assert state.machine_state.stack is not machine.stack


@pytest.mark.parametrize("value", [-(10**100), 0, 10**100])
def test_signed_core_literals_are_immediates_without_frontend_negation(value):
    expression = CoreInt(value)
    state, config = literal_demo(expression, Strategy.CBNEED, TraceMode.FULL)
    result = step(state, config)
    assert result.next_state.machine_state.control.reference.value is value
    assert result.next_state.machine_state.heap.current_slots == 0


@pytest.mark.parametrize("source", [
    "f x = 10\nf [] = unknown\nmain = 42",
    "f [] = 10\nf [] = unknown\nmain = 42",
    "main = if True then 42 else unknown",
])
def test_source_names_are_checked_even_when_literal_demo_would_ignore_them(source):
    with pytest.raises(NameResolutionError, match="unknown"):
        compile_source(source)


def test_deep_compiled_primitive_starts_iteratively():
    program = compile_source(
        "main = " + " + ".join("1" for _ in range(2000))
    )

    expression = program.bindings[0].rhs
    state, config = literal_demo(
        expression,
        Strategy.CBNEED,
        TraceMode.FULL,
    )

    transition = step(state, config)
    machine = transition.next_state.machine_state

    assert transition.rule_id == "CORE_EVAL_PRIMITIVE_START"
    assert isinstance(
        machine.stack.peek(),
        PrimitiveOperandsFrame,
    )
    assert isinstance(machine.control, EvaluateCore)

    assert state.transition_index == 0
    assert state.machine_state.stack.depth == 0
