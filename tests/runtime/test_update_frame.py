
from dataclasses import FrozenInstanceError, replace

import pytest

from lazy_lab.pipeline import compile_source
from lazy_lab.engine.core_machine import create_initial_core_state
from lazy_lab.runtime.environment import Environment
from lazy_lab.runtime.heap import Heap, Reserved, Indirection
from lazy_lab.runtime.references import ImmediateInteger
from lazy_lab.runtime.stack import UpdateFrame, Stack
from lazy_lab.runtime.state import (
    ExecutionConfig,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)


def test_update_frame_preserves_anchor_and_caller_environment():
    heap = Heap()
    anchor = heap.allocate(Reserved(), allocated_slots=1)

    caller_env = Environment({"x": ImmediateInteger(10)})

    frame = UpdateFrame(
        thunk_reference=anchor,
        return_environment=caller_env,
    )

    assert frame.thunk_reference is anchor
    assert frame.return_environment is caller_env
    assert frame.awaiting_whnf is False


def test_update_frame_stage_change_is_immutable():
    heap = Heap()
    anchor = heap.allocate(Reserved(), allocated_slots=1)

    caller_env = Environment()

    initial = UpdateFrame(
        thunk_reference=anchor,
        return_environment=caller_env,
    )

    awaiting = replace(initial, awaiting_whnf=True)

    assert initial.awaiting_whnf is False
    assert awaiting.awaiting_whnf is True

    assert awaiting.thunk_reference is anchor
    assert awaiting.return_environment is caller_env

    with pytest.raises(FrozenInstanceError):
        initial.awaiting_whnf = True


@pytest.mark.parametrize(
    "invalid_reference",
    [None, ImmediateInteger(10), "anchor"],
)
def test_update_frame_rejects_invalid_anchor(invalid_reference):
    with pytest.raises(TypeError):
        UpdateFrame(
            thunk_reference=invalid_reference,
            return_environment=Environment(),
        )


def test_update_frame_rejects_invalid_environment():
    heap = Heap()
    anchor = heap.allocate(Reserved(), allocated_slots=1)

    with pytest.raises(TypeError):
        UpdateFrame(
            thunk_reference=anchor,
            return_environment=None,
        )


@pytest.mark.parametrize("invalid_stage", [None, 0, 1, "yes"])
def test_update_frame_requires_boolean_demand_stage(invalid_stage):
    heap = Heap()
    anchor = heap.allocate(Reserved(), allocated_slots=1)

    with pytest.raises(TypeError):
        UpdateFrame(
            thunk_reference=anchor,
            return_environment=Environment(),
            awaiting_whnf=invalid_stage,
        )


def test_nested_update_frames_preserve_snapshot_isolation():
    config = ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=100,
        result_node_limit=100,
        trace_mode=TraceMode.FULL,
    )

    initial = create_initial_core_state(
        compile_source("main = 42"),
        config,
        session_id="nested-update-frames",
    )

    machine = initial.machine_state

    outer_ref = machine.heap.allocate(
        Reserved(), allocated_slots=1
    )
    inner_ref = machine.heap.allocate(
        Reserved(), allocated_slots=1
    )

    outer_frame = UpdateFrame(
        thunk_reference=outer_ref,
        return_environment=machine.global_environment,
    )
    inner_frame = UpdateFrame(
        thunk_reference=inner_ref,
        return_environment=machine.global_environment,
    )

    machine.stack.push(outer_frame)
    machine.stack.push(inner_frame)

    snapshot = initial.snapshot()

    assert snapshot.machine_state.stack is not machine.stack
    assert snapshot.machine_state.heap is not machine.heap

    assert snapshot.machine_state.stack.depth == 2
    assert snapshot.machine_state.stack.peek() is inner_frame

    # Changes in the cloned stack do not change the original.
    assert snapshot.machine_state.stack.pop() is inner_frame
    assert snapshot.machine_state.stack.peek() is outer_frame

    assert machine.stack.depth == 2
    assert machine.stack.peek() is inner_frame

    # Changes in the cloned heap do not modify historical cells.
    snapshot.machine_state.heap.replace(
        outer_ref,
        Indirection(ImmediateInteger(42)),
    )

    assert isinstance(
        machine.heap.get(outer_ref).value, Reserved
    )
    assert isinstance(
        snapshot.machine_state.heap.get(outer_ref).value,
        Indirection,
    )
