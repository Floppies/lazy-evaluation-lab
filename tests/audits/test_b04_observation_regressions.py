"""Focused B04 execution properties established during the formal audit."""

import pytest

from lazy_lab.engine.core_machine import create_initial_core_state, step
from lazy_lab.engine.session_runner import run_session_batch
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.closures import Closure
from lazy_lab.runtime.control import ApplyPrimitive
from lazy_lab.runtime.heap import Indirection, Reserved
from lazy_lab.runtime.references import ImmediateBoolean, ImmediateInteger
from lazy_lab.runtime.stack import LocalValueInitializationFrame
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionStatus,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.runtime.transitions import RuleId


def test_error_after_partial_letrec_initialization_preserves_snapshot():
    program = compile_source(
        "main = let { x = 10; good y = x + y; bad = good True } in good 1"
    )
    config = ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBV,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=200,
        result_node_limit=1,
        trace_mode=TraceMode.FULL,
    )
    initial = create_initial_core_state(
        program, config, session_id="b04-partial-initialization-error",
    )
    current = initial
    rules = []
    for _ in range(config.execution_step_limit):
        if isinstance(current.machine_state.control, ApplyPrimitive):
            break
        transition = step(current, config)
        rules.append(transition.rule_id)
        current = transition.next_state
    else:
        pytest.fail("The compiled program did not reach primitive execution")

    machine = current.machine_state
    assert machine.control == ApplyPrimitive(
        "+", (ImmediateInteger(10), ImmediateBoolean(True)),
    )
    assert rules.count(RuleId.CORE_LETREC_STORE_VALUE) == 1
    assert RuleId.CORE_LETREC_INSTALL_FUNCTION in rules

    initialization_frames = [
        frame for frame in machine.stack.frames
        if isinstance(frame, LocalValueInitializationFrame)
    ]
    assert len(initialization_frames) == 1
    initializing = initialization_frames[0]
    environment = initializing.environment
    assert initializing.binding_reference is environment.lookup("bad")
    assert isinstance(machine.heap.get(initializing.binding_reference).value, Reserved)
    x_reference = environment.lookup("x")
    assert machine.heap.get(x_reference).value == Indirection(ImmediateInteger(10))
    good_binding = machine.heap.get(environment.lookup("good")).value
    assert isinstance(good_binding, Indirection)
    closure = machine.heap.get(good_binding.target).value
    assert isinstance(closure, Closure)
    assert closure.captured_locals.lookup("x") is x_reference

    saved = current.snapshot()
    cells = dict(machine.heap.cells)
    frames = machine.stack.frames
    counters = (
        current.state_id, current.transition_index,
        machine.evaluator_transition_count, machine.heap.next_object_id,
        machine.heap.current_slots,
    )

    for advance in (
        lambda: step(current, config),
        lambda: run_session_batch(current, config, max_steps=1),
    ):
        with pytest.raises(TypeError, match="requires integer operands"):
            advance()

        assert current.machine_state is machine
        assert machine.control is saved.machine_state.control
        assert machine.local_environment is saved.machine_state.local_environment
        assert machine.global_environment is saved.machine_state.global_environment
        assert machine.result_state is saved.machine_state.result_state
        assert machine.status is ExecutionStatus.RUNNING
        assert current.canonical_result is None
        assert dict(machine.heap.cells) == cells == dict(saved.machine_state.heap.cells)
        assert machine.stack.frames == frames == saved.machine_state.stack.frames
        assert (
            current.state_id, current.transition_index,
            machine.evaluator_transition_count, machine.heap.next_object_id,
            machine.heap.current_slots,
        ) == counters

    assert initial.transition_index == 0
    assert initial.machine_state.heap.current_slots == 0
    assert initial.machine_state.stack.depth == 0
