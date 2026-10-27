"""Deep operational execution checks added by the B04 audit."""

import pytest

from lazy_lab.core.nodes import (
    CoreApp,
    CoreBinding,
    CoreInt,
    CoreLam,
    CoreLetRec,
    CoreProgram,
    CoreVar,
)
from lazy_lab.core.validation import validate_core_program
from lazy_lab.engine.core_machine import create_initial_core_state
from lazy_lab.engine.session_runner import run_session_batch
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
from lazy_lab.semantics.name_resolution import check_core_names


@pytest.mark.parametrize("shape", ["applications", "scopes", "global_aliases"])
def test_deep_cbv_execution_resumes_without_python_recursion(shape):
    depth = 1200
    expression = CoreInt(42)
    expected = CanonicalInteger(42)
    if shape == "applications":
        for _ in range(depth):
            expression = CoreApp(CoreLam("x", CoreVar("x")), expression)
        bindings = (CoreBinding("main", expression),)
    elif shape == "scopes":
        expression = CoreVar("x")
        for value in range(depth):
            expression = CoreLetRec(
                (CoreBinding("x", CoreInt(value)),), expression,
            )
        bindings = (CoreBinding("main", expression),)
        expected = CanonicalInteger(0)
    else:
        bindings = tuple(
            CoreBinding(f"g{index}", CoreVar(f"g{index + 1}"))
            for index in range(depth)
        ) + (
            CoreBinding(f"g{depth}", CoreInt(42)),
            CoreBinding("main", CoreVar("g0")),
        )

    program = CoreProgram(bindings)
    validate_core_program(program)
    check_core_names(program)
    config = ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBV,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=40000,
        result_node_limit=1,
        trace_mode=TraceMode.METRICS_ONLY,
    )
    initial = create_initial_core_state(program, config, session_id="b04-deep")
    full = run_session_batch(initial, config, max_steps=40000)
    # Global aliases first require installing the entire global group.
    pause_steps = 2 * depth + 5 if shape == "global_aliases" else depth + 5
    paused = run_session_batch(initial, config, max_steps=pause_steps)
    assert paused.stop_reason is BatchStopReason.BATCH_LIMIT
    assert paused.state.machine_state.stack.depth > 0
    cells = dict(paused.state.machine_state.heap.cells)
    frames = paused.state.machine_state.stack.frames
    slots = paused.state.machine_state.heap.current_slots
    next_id = paused.state.machine_state.heap.next_object_id
    resumed = run_session_batch(paused.state, config, max_steps=40000)

    for result in (full, resumed):
        machine = result.state.machine_state
        assert result.stop_reason is BatchStopReason.TERMINAL_STATUS
        assert result.state.canonical_result == expected
        assert machine.status is ExecutionStatus.COMPLETED
        assert machine.stack.depth == 0
        assert machine.local_environment is machine.global_environment
        assert result.trace == ()
        assert result.state.transition_index == full.state.transition_index
        assert machine.evaluator_transition_count == full.state.machine_state.evaluator_transition_count
        assert machine.heap.current_slots == full.state.machine_state.heap.current_slots
        assert machine.heap.next_object_id == full.state.machine_state.heap.next_object_id
        assert sum(cell.allocated_slots for cell in machine.heap.cells.values()) == machine.heap.current_slots
        assert all(
            cell.allocated_slots == cell.value.required_slots
            for cell in machine.heap.cells.values()
        )

    assert dict(paused.state.machine_state.heap.cells) == cells
    # Compare shared immutable frame identities, not deeply nested Core trees.
    assert len(paused.state.machine_state.stack.frames) == len(frames)
    assert all(
        current is previous
        for current, previous in zip(paused.state.machine_state.stack.frames, frames)
    )
    assert paused.state.machine_state.heap.current_slots == slots
    assert paused.state.machine_state.heap.next_object_id == next_id
    assert paused.state.canonical_result is None
    assert paused.state.machine_state.status is ExecutionStatus.RUNNING
    assert initial.transition_index == 0
    assert initial.machine_state.heap.current_slots == 0
    assert initial.machine_state.stack.depth == 0
