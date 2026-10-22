"""Structural continuation contracts for the Core evaluator."""

from dataclasses import FrozenInstanceError

import pytest

from lazy_lab.core.nodes import CoreInt, CoreVar
from lazy_lab.runtime.control import EvaluateCore
from lazy_lab.runtime.environment import Environment
from lazy_lab.runtime.heap import Heap
from lazy_lab.runtime.references import ImmediateInteger
from lazy_lab.runtime.stack import (
    ApplyArgumentFrame,
    ApplyFunctionFrame,
    IfFrame,
    Stack,
)
from lazy_lab.runtime.state import (
    ExecutionPhase,
    ExecutionState,
    ExecutionStatus,
    MachineKind,
    MachineState,
    Strategy,
)


def test_application_frame_preserves_call_site_context():
    environment = Environment({
        "x": ImmediateInteger(10),
    })
    argument = CoreVar("x")

    frame = ApplyFunctionFrame(argument, environment)

    assert frame.argument is argument
    assert frame.environment is environment
    assert frame.environment.lookup("x") == ImmediateInteger(10)


def test_argument_frame_preserves_function_reference():
    reference = ImmediateInteger(7)
    frame = ApplyArgumentFrame(reference)

    assert frame.function is reference


def test_if_frame_preserves_branches_and_environment():
    environment = Environment({
        "x": ImmediateInteger(3),
    })
    then_branch = CoreVar("x")
    else_branch = CoreInt(0)

    frame = IfFrame(
        then_branch,
        else_branch,
        environment,
    )

    assert frame.then_branch is then_branch
    assert frame.else_branch is else_branch
    assert frame.environment is environment


def test_continuation_frames_are_immutable():
    frame = ApplyFunctionFrame(
        CoreInt(5),
        Environment(),
    )

    with pytest.raises(FrozenInstanceError):
        frame.argument = CoreInt(10)


def test_nested_continuations_preserve_lifo_order():
    environment = Environment()
    outer = IfFrame(
        CoreInt(1),
        CoreInt(2),
        environment,
    )
    inner = ApplyFunctionFrame(
        CoreInt(3),
        environment,
    )

    stack = Stack()
    stack.push(outer)
    stack.push(inner)

    assert stack.depth == 2
    assert stack.pop() is inner
    assert stack.pop() is outer
    assert stack.depth == 0


def test_snapshot_preserves_independent_continuation_stack():
    environment = Environment()
    frame = ApplyFunctionFrame(
        CoreInt(5),
        environment,
    )

    stack = Stack()
    stack.push(frame)

    machine = MachineState(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBV,
        status=ExecutionStatus.RUNNING,
        phase=ExecutionPhase.EVALUATION,
        control=EvaluateCore(CoreInt(42)),
        local_environment=environment,
        global_environment=environment,
        heap=Heap(),
        stack=stack,
    )

    state = ExecutionState(
        state_id=0,
        session_id="continuation-test",
        transition_index=0,
        machine_state=machine,
    )

    snapshot = state.snapshot()

    assert snapshot.machine_state.stack is not stack
    assert snapshot.machine_state.stack.peek() is frame

    stack.pop()

    assert stack.depth == 0
    assert snapshot.machine_state.stack.depth == 1
    assert snapshot.machine_state.stack.peek() is frame
