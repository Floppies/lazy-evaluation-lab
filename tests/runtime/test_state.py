from dataclasses import replace

import pytest

from lazy_lab.core.nodes import CoreInt, CoreVar
from lazy_lab.runtime.control import EvaluateCore, Force, Return
from lazy_lab.runtime.environment import Environment
from lazy_lab.runtime.heap import Heap, Indirection, Reserved
from lazy_lab.runtime.references import ImmediateInteger
from lazy_lab.runtime.stack import ApplyFunctionFrame, Stack
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionPhase,
    ExecutionState,
    ExecutionStatus,
    InstrumentationState,
    MachineKind,
    MachineState,
    ResultPolicy,
    Strategy,
    TraceMode,
)


def make_state() -> ExecutionState:
    heap = Heap()
    reference = heap.allocate(Reserved(), allocated_slots=1)

    globals_env = Environment({"x": reference})

    machine = MachineState(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        status=ExecutionStatus.RUNNING,
        phase=ExecutionPhase.EVALUATION,
        control=EvaluateCore(CoreVar("x")),
        local_environment=globals_env,
        global_environment=globals_env,
        heap=heap,
        stack=Stack(),
    )

    return ExecutionState(
        state_id=0,
        session_id="test-session",
        transition_index=0,
        machine_state=machine,
        instrumentation_state=InstrumentationState(),
    )


def test_initial_machine_state():
    state = make_state()
    machine = state.machine_state

    assert state.state_id == 0
    assert state.transition_index == 0
    assert machine.strategy is Strategy.CBNEED
    assert machine.status is ExecutionStatus.RUNNING
    assert machine.phase is ExecutionPhase.EVALUATION
    assert isinstance(machine.control, EvaluateCore)
    assert machine.next_object_id == 1


def test_snapshot_preserves_heap_contents():
    state = make_state()
    snapshot = state.snapshot()

    reference = state.machine_state.global_environment.lookup("x")

    state.machine_state.heap.replace(
        reference,
        Indirection(ImmediateInteger(42)),
    )

    assert isinstance(
        snapshot.machine_state.heap.get(reference).value,
        Reserved,
    )

    assert isinstance(
        state.machine_state.heap.get(reference).value,
        Indirection,
    )


def test_snapshot_preserves_stack():
    state = make_state()
    snapshot = state.snapshot()

    frame = ApplyFunctionFrame(
        argument=CoreInt(5),
        environment=Environment(),
    )

    state.machine_state.stack.push(frame)

    assert state.machine_state.stack.depth == 1
    assert snapshot.machine_state.stack.depth == 0


def test_snapshot_preserves_logical_identity():
    state = make_state()
    snapshot = state.snapshot()

    assert snapshot.state_id == state.state_id
    assert snapshot.session_id == state.session_id
    assert snapshot.transition_index == state.transition_index

    assert snapshot is not state
    assert snapshot.machine_state.heap is not state.machine_state.heap
    assert snapshot.machine_state.stack is not state.machine_state.stack


def test_status_is_independent_of_phase():
    state = make_state()

    completed = replace(
        state.machine_state,
        status=ExecutionStatus.COMPLETED,
    )

    assert completed.phase is ExecutionPhase.EVALUATION
    assert completed.status is ExecutionStatus.COMPLETED
    assert state.machine_state.status is ExecutionStatus.RUNNING


def test_core_control_variants():
    reference = ImmediateInteger(42)

    return_control = Return(reference)
    force_control = Force(reference)

    assert return_control.reference is reference
    assert force_control.reference is reference


def test_config_rejects_invalid_machine_strategy():
    with pytest.raises(ValueError):
        ExecutionConfig(
            machine_kind=MachineKind.STG,
            strategy=Strategy.CBV,
            result_policy=ResultPolicy.WHNF_ONLY,
            execution_step_limit=1000,
            result_node_limit=100,
            trace_mode=TraceMode.FULL,
        )


@pytest.mark.parametrize("strategy", list(Strategy))
def test_config_accepts_core_strategy(strategy):
    config = ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=strategy,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=1000,
        result_node_limit=100,
        trace_mode=TraceMode.FULL,
    )

    assert config.strategy is strategy


@pytest.mark.parametrize(
    "field_name, invalid_value",
    [
        ("state_id", -1),
        ("transition_index", -1),
        ("session_id", ""),
    ],
)
def test_invalid_state_identity(field_name, invalid_value):
    state = make_state()

    with pytest.raises(ValueError):
        replace(state, **{field_name: invalid_value})

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

@pytest.mark.parametrize("strategy", list(Strategy))
def test_core_accepts_each_evaluation_strategy(strategy):
    config = ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=strategy,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=100,
        result_node_limit=100,
        trace_mode=TraceMode.FULL,
    )

    assert config.strategy is strategy