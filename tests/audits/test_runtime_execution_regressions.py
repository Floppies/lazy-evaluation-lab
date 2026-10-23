"""State, transition, and bounded-execution checks scoped to B03."""

from dataclasses import FrozenInstanceError, replace

import pytest

from lazy_lab.core.nodes import CoreBool, CoreInt
from lazy_lab.engine.core_machine import (
    EvaluatorBudgetExhaustedError,
    InvalidMachineStateError,
    UnsupportedTransitionError,
    run_batch,
    step,
)
from lazy_lab.runtime.control import EvaluateCore, Force, InitializeCoreBindings, Return
from lazy_lab.runtime.environment import Environment
from lazy_lab.runtime.heap import Heap, Indirection, Reserved
from lazy_lab.runtime.references import ImmediateBoolean, ImmediateInteger
from lazy_lab.runtime.stack import ApplyArgumentFrame, Stack
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
from lazy_lab.runtime.transitions import BatchStopReason, TraceEntry, TransitionKind


def make_config(**changes):
    config = ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=100,
        result_node_limit=100,
        trace_mode=TraceMode.FULL,
    )
    return replace(config, **changes)


def make_state(**machine_changes):
    heap = Heap()
    reference = heap.allocate(Reserved(), allocated_slots=3)
    environment = Environment({"recursive": reference})
    machine = MachineState(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        status=ExecutionStatus.RUNNING,
        phase=ExecutionPhase.EVALUATION,
        control=EvaluateCore(CoreInt(42)),
        local_environment=environment,
        global_environment=environment,
        heap=heap,
        stack=Stack(),
    )
    return ExecutionState(
        state_id=17,
        session_id="b03-audit",
        transition_index=81,
        machine_state=replace(machine, **machine_changes),
    )


@pytest.mark.parametrize("field,value", [
    ("machine_kind", "CORE"),
    ("strategy", "CBNEED"),
    ("result_policy", "WHNF_ONLY"),
    ("trace_mode", "FULL"),
])
def test_config_requires_enum_values(field, value):
    with pytest.raises(TypeError):
        make_config(**{field: value})


@pytest.mark.parametrize("field", ["execution_step_limit", "result_node_limit"])
@pytest.mark.parametrize("value", [0, -1, True, 1.5, None, "1"])
def test_config_requires_positive_exact_integer_limits(field, value):
    with pytest.raises(ValueError):
        make_config(**{field: value})


@pytest.mark.parametrize("kind,strategy", [
    (MachineKind.CORE, Strategy.CBV),
    (MachineKind.CORE, Strategy.CBN),
    (MachineKind.CORE, Strategy.CBNEED),
    (MachineKind.STG, Strategy.CBNEED),
])
@pytest.mark.parametrize("policy", list(ResultPolicy))
def test_supported_configuration_combinations(kind, strategy, policy):
    config = make_config(machine_kind=kind, strategy=strategy, result_policy=policy)
    assert config.machine_kind is kind
    assert config.strategy is strategy
    with pytest.raises(FrozenInstanceError):
        config.strategy = Strategy.CBV


def test_stg_cbn_is_invalid_configuration():
    with pytest.raises(ValueError):
        make_config(machine_kind=MachineKind.STG, strategy=Strategy.CBN)


@pytest.mark.parametrize("value", [-1, True, 1.5, None])
def test_evaluator_counter_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        make_state(evaluator_transition_count=value)


@pytest.mark.parametrize("field", ["state_id", "transition_index"])
@pytest.mark.parametrize("value", [-1, True, 1.5, None])
def test_logical_counters_require_nonnegative_exact_integers(field, value):
    with pytest.raises(ValueError):
        replace(make_state(), **{field: value})


@pytest.mark.parametrize("value", [None, 1, ""])
def test_session_id_is_nonempty_string(value):
    with pytest.raises(ValueError):
        replace(make_state(), session_id=value)


def test_snapshot_isolation_with_builtin_payloads_and_shared_immutable_graph():
    state = make_state()
    machine = state.machine_state
    reference = machine.local_environment.lookup("recursive")
    frame = ApplyArgumentFrame(reference)
    machine.stack.push(frame)
    snapshot = state.snapshot()
    saved = snapshot.machine_state
    assert (snapshot.state_id, snapshot.transition_index, snapshot.session_id) == (17, 81, "b03-audit")
    assert snapshot.instrumentation_state is state.instrumentation_state
    assert saved.control is machine.control
    assert saved.local_environment is machine.local_environment
    assert saved.global_environment is machine.global_environment
    assert saved.stack.peek() is frame
    assert saved.heap.get(reference) is machine.heap.get(reference)
    saved.heap.replace(reference, Indirection(ImmediateInteger(1)))
    saved.stack.pop()
    assert isinstance(machine.heap.get(reference).value, Reserved)
    assert machine.stack.peek() is frame
    machine.heap.allocate(Reserved(), allocated_slots=2)
    assert machine.next_object_id == 2
    assert saved.next_object_id == 1
    assert saved.heap.current_slots == 3
    assert saved.local_environment.lookup("recursive") is reference


def test_transition_preserves_existing_storage_and_independent_logical_counters():
    state = make_state(evaluator_transition_count=4)
    machine = state.machine_state
    reference = machine.global_environment.lookup("recursive")
    frame = ApplyArgumentFrame(reference)
    machine.stack.push(frame)
    transition = step(state, make_config())
    successor = transition.next_state
    assert (successor.state_id, successor.transition_index) == (18, 82)
    assert successor.machine_state.evaluator_transition_count == 5
    assert transition.previous_state_id == 17
    assert transition.phase_before is transition.phase_after is ExecutionPhase.EVALUATION
    assert transition.transition_kind is TransitionKind.EVALUATOR
    assert transition.source_origins == ()
    assert successor.machine_state.status is ExecutionStatus.RUNNING
    assert successor.machine_state.heap.current_slots == 3
    assert successor.machine_state.next_object_id == 1
    successor.machine_state.heap.replace(reference, Indirection(ImmediateInteger(7)))
    successor.machine_state.stack.pop()
    assert isinstance(machine.heap.get(reference).value, Reserved)
    assert machine.stack.peek() is frame
    assert isinstance(machine.control, EvaluateCore)
    assert machine.evaluator_transition_count == 4
    entry = TraceEntry.from_transition(transition)
    assert (entry.previous_state_id, entry.next_state_id) == (17, 18)
    assert entry.rule_id == transition.rule_id
    assert entry.phase_before is transition.phase_before
    assert entry.phase_after is transition.phase_after


@pytest.mark.parametrize("status", [s for s in ExecutionStatus if s is not ExecutionStatus.RUNNING])
def test_all_terminal_statuses_stop_without_transition(status):
    state = make_state(status=status, control=Return(ImmediateInteger(1)), evaluator_transition_count=100)
    config = make_config()
    with pytest.raises(InvalidMachineStateError):
        step(state, config)
    batch = run_batch(state, config, max_steps=1)
    assert batch.state is state
    assert batch.trace == ()
    assert batch.stop_reason is BatchStopReason.TERMINAL_STATUS


def test_incomplete_initialization_control_is_rejected():
    state = make_state(control=InitializeCoreBindings(()))
    for advance in [lambda: step(state, make_config()), lambda: run_batch(state, make_config(), max_steps=2)]:
        with pytest.raises(UnsupportedTransitionError):
            advance()
    assert state.transition_index == 81
    assert state.machine_state.evaluator_transition_count == 0


def test_return_with_pending_stack_is_not_completed():
    state = make_state(control=Return(ImmediateInteger(1)))
    state.machine_state.stack.push(ApplyArgumentFrame(ImmediateInteger(2)))
    with pytest.raises(UnsupportedTransitionError):
        run_batch(state, make_config(), max_steps=2)
    assert state.machine_state.status is ExecutionStatus.RUNNING
    assert state.machine_state.stack.depth == 1


@pytest.mark.parametrize("max_steps", [1, 2, 100])
def test_pending_observation_beats_batch_and_evaluator_limits(max_steps):
    state = make_state()
    config = make_config(execution_step_limit=1)
    batch = run_batch(state, config, max_steps=max_steps)
    assert batch.stop_reason is BatchStopReason.WHNF_PENDING
    assert batch.state.machine_state.evaluator_transition_count == 1
    assert batch.state.transition_index == 82
    assert len(batch.trace) == 1
    again = run_batch(batch.state, config, max_steps=max_steps)
    assert again.state is batch.state
    assert again.trace == ()
    assert again.stop_reason is BatchStopReason.WHNF_PENDING


@pytest.mark.parametrize("limit,reason", [(1, BatchStopReason.EVALUATOR_BUDGET), (2, BatchStopReason.BATCH_LIMIT)])
def test_batch_bound_and_evaluator_budget_are_distinct(limit, reason):
    state = make_state()
    state.machine_state.stack.push(ApplyArgumentFrame(ImmediateInteger(1)))
    config = make_config(execution_step_limit=limit)
    batch = run_batch(state, config, max_steps=1)
    assert batch.stop_reason is reason
    assert batch.state.machine_state.evaluator_transition_count == 1
    assert batch.state.transition_index == 82
    if limit == 1:
        again = run_batch(batch.state, config, max_steps=10)
        assert again.state is batch.state
        assert again.trace == ()
        assert again.stop_reason is BatchStopReason.EVALUATOR_BUDGET


def test_exhausted_evaluator_budget_prevents_literal_dispatch():
    state = make_state(evaluator_transition_count=2)
    config = make_config(execution_step_limit=2)
    with pytest.raises(EvaluatorBudgetExhaustedError):
        step(state, config)
    batch = run_batch(state, config, max_steps=2)
    assert batch.state is state
    assert batch.trace == ()
    assert batch.stop_reason is BatchStopReason.EVALUATOR_BUDGET


@pytest.mark.parametrize("size", [0, -1, True, 1.5, None, "1"])
def test_batch_size_validation_precedes_configuration_validation(size):
    state = make_state(strategy=Strategy.CBV)
    with pytest.raises(ValueError, match="max_steps"):
        run_batch(state, make_config(), max_steps=size)


def test_configuration_mismatch_precedes_terminal_and_budget_checks():
    state = make_state(status=ExecutionStatus.COMPLETED, evaluator_transition_count=100)
    config = make_config(strategy=Strategy.CBV)
    with pytest.raises(ValueError, match="does not match"):
        step(state, config)
    with pytest.raises(ValueError, match="does not match"):
        run_batch(state, config, max_steps=1)


@pytest.mark.parametrize("count", [99, 100])
def test_force_immediate_respects_evaluator_budget(count):
    reference = ImmediateInteger(1)
    state = make_state(control=Force(reference), evaluator_transition_count=count)
    config = make_config(execution_step_limit=100)

    if count < config.execution_step_limit:
        transition = step(state, config)
        assert transition.rule_id == "CORE_FORCE_IMMEDIATE"
        assert transition.next_state.machine_state.control == Return(reference)
        assert transition.next_state.machine_state.evaluator_transition_count == count + 1
        assert transition.next_state.transition_index == 82
    else:
        with pytest.raises(EvaluatorBudgetExhaustedError):
            step(state, config)
        batch = run_batch(state, config, max_steps=1)
        assert batch.stop_reason is BatchStopReason.EVALUATOR_BUDGET
        assert batch.state is state
        assert batch.trace == ()

    assert state.transition_index == 81
    assert state.machine_state.control == Force(reference)
    assert state.machine_state.evaluator_transition_count == count


@pytest.mark.parametrize("api", [step, run_batch])
def test_machine_kind_mismatch_is_explicit(api):
    kwargs = {"max_steps": 1} if api is run_batch else {}
    with pytest.raises(ValueError, match="does not match"):
        api(make_state(), make_config(machine_kind=MachineKind.STG), **kwargs)


@pytest.mark.parametrize("api", [step, run_batch])
def test_stg_is_rejected_even_when_no_transition_would_be_needed(api):
    state = make_state(machine_kind=MachineKind.STG, status=ExecutionStatus.COMPLETED)
    kwargs = {"max_steps": 1} if api is run_batch else {}
    with pytest.raises(UnsupportedTransitionError, match="STG"):
        api(state, make_config(machine_kind=MachineKind.STG), **kwargs)


def test_trace_modes_preserve_full_supported_machine_projection():
    state = make_state(control=EvaluateCore(CoreBool(False)))
    batches = [run_batch(state, make_config(trace_mode=mode), max_steps=3) for mode in TraceMode]
    for batch in batches:
        machine = batch.state.machine_state
        assert machine.control == Return(ImmediateBoolean(False))
        assert machine.heap.current_slots == 3
        assert machine.next_object_id == 1
        assert machine.stack.depth == 0
        assert machine.local_environment is state.machine_state.local_environment
        assert machine.global_environment is state.machine_state.global_environment
        assert machine.phase is ExecutionPhase.EVALUATION
        assert machine.status is ExecutionStatus.RUNNING
        assert machine.evaluator_transition_count == 1
        assert (batch.state.state_id, batch.state.transition_index) == (18, 82)
        assert batch.stop_reason is BatchStopReason.WHNF_PENDING
    assert batches[0].trace == batches[1].trace
    assert len(batches[0].trace) == 1
    assert batches[2].trace == ()
