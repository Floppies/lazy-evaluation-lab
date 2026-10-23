from dataclasses import replace

import pytest

from lazy_lab.core.nodes import (
    CoreApp,
    CoreBool,
    CoreInt,
    CoreLam,
    CoreVar,
    CorePrimOp,
)
from lazy_lab.engine.core_machine import (
    EvaluatorBudgetExhaustedError,
    InvalidMachineStateError,
    UnsupportedTransitionError,
    run_batch,
    step,
)
from lazy_lab.runtime.control import EvaluateCore, Return
from lazy_lab.runtime.environment import Environment, UnboundNameError
from lazy_lab.runtime.heap import Heap
from lazy_lab.runtime.references import (
    ImmediateBoolean,
    ImmediateInteger,
)
from lazy_lab.runtime.stack import Stack, ApplyFunctionFrame
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
from lazy_lab.runtime.transitions import (
    BatchStopReason,
    TransitionKind,
)
from lazy_lab.runtime.closures import Closure

def make_config(
    trace_mode=TraceMode.FULL,
    step_limit=100,
):
    return ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=step_limit,
        result_node_limit=100,
        trace_mode=trace_mode,
    )


def make_state(expression):
    environment = Environment()

    machine = MachineState(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        status=ExecutionStatus.RUNNING,
        phase=ExecutionPhase.EVALUATION,
        control=EvaluateCore(expression),
        local_environment=environment,
        global_environment=environment,
        heap=Heap(),
        stack=Stack(),
    )

    return ExecutionState(
        state_id=0,
        session_id="test-session",
        transition_index=0,
        machine_state=machine,
    )


def test_integer_transition():
    state = make_state(CoreInt(42))

    transition = step(state, make_config())
    next_state = transition.next_state

    assert transition.rule_id == "CORE_EVAL_INTEGER"
    assert transition.transition_kind is TransitionKind.EVALUATOR
    assert transition.previous_state_id == 0

    assert next_state.state_id == 1
    assert next_state.transition_index == 1

    assert next_state.machine_state.control == Return(
        ImmediateInteger(42)
    )

    assert next_state.machine_state.evaluator_transition_count == 1
    assert next_state.machine_state.heap.current_slots == 0
    assert next_state.machine_state.stack.depth == 0

    assert transition.semantic_events == ()
    assert transition.heap_effects == ()
    assert transition.stack_effects == ()


def test_boolean_transition():
    state = make_state(CoreBool(True))

    transition = step(state, make_config())

    assert transition.rule_id == "CORE_EVAL_BOOLEAN"
    assert transition.next_state.machine_state.control == Return(
        ImmediateBoolean(True)
    )


def test_previous_state_is_unchanged():
    state = make_state(CoreInt(42))

    transition = step(state, make_config())

    assert state.state_id == 0
    assert state.transition_index == 0
    assert state.machine_state.evaluator_transition_count == 0
    assert isinstance(state.machine_state.control, EvaluateCore)

    assert transition.next_state is not state
    assert (
        transition.next_state.machine_state.heap
        is not state.machine_state.heap
    )


def test_batch_stops_at_pending_result():
    result = run_batch(
        make_state(CoreInt(42)),
        make_config(),
        max_steps=10,
    )

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert len(result.trace) == 1
    assert result.trace[0].rule_id == "CORE_EVAL_INTEGER"
    assert result.state.machine_state.status is ExecutionStatus.RUNNING


def test_metrics_only_omits_trace_records():
    result = run_batch(
        make_state(CoreInt(42)),
        make_config(trace_mode=TraceMode.METRICS_ONLY),
        max_steps=10,
    )

    assert result.trace == ()
    assert result.state.transition_index == 1
    assert isinstance(result.state.machine_state.control, Return)


def test_step_budget_is_enforced():
    state = make_state(CoreInt(42))

    exhausted_machine = replace(
        state.machine_state,
        evaluator_transition_count=1,
    )

    exhausted_state = replace(
        state,
        machine_state=exhausted_machine,
    )

    config = make_config(step_limit=1)

    with pytest.raises(EvaluatorBudgetExhaustedError):
        step(exhausted_state, config)

    result = run_batch(
        exhausted_state,
        config,
        max_steps=10,
    )

    assert result.stop_reason is BatchStopReason.EVALUATOR_BUDGET
    assert result.state.transition_index == 0
    assert result.trace == ()


def test_unsupported_primitive_does_not_advance():
    state = make_state(
        CorePrimOp(
            "+",
            (CoreInt(1), CoreInt(2)),
        )
    )

    with pytest.raises(
        UnsupportedTransitionError,
        match="CorePrimOp",
    ):
        step(state, make_config())

    assert state.transition_index == 0
    assert state.machine_state.stack.depth == 0
    assert state.machine_state.evaluator_transition_count == 0


def test_terminal_state_cannot_advance():
    state = make_state(CoreInt(42))

    terminal_machine = replace(
        state.machine_state,
        status=ExecutionStatus.COMPLETED,
    )

    terminal_state = replace(
        state,
        machine_state=terminal_machine,
    )

    with pytest.raises(InvalidMachineStateError):
        step(terminal_state, make_config())


def test_invalid_batch_size():
    with pytest.raises(ValueError):
        run_batch(
            make_state(CoreInt(42)),
            make_config(),
            max_steps=0,
        )


def test_second_literal_step_is_not_implemented():
    first = step(make_state(CoreInt(42)), make_config())

    with pytest.raises(UnsupportedTransitionError):
        step(first.next_state, make_config())


def test_lambda_transition_allocates_closure():
    global_env = Environment({
        "global_value": ImmediateInteger(100),
    })

    local_env = global_env.extend({
        "x": ImmediateInteger(10),
    })

    expression = CoreLam(
        "argument",
        CoreVar("x"),
    )

    original = make_state(expression)
    original = replace(
        original,
        machine_state=replace(
            original.machine_state,
            local_environment=local_env,
            global_environment=global_env,
        ),
    )

    transition = step(original, make_config())
    machine = transition.next_state.machine_state

    assert transition.rule_id == "CORE_EVAL_LAMBDA"
    assert isinstance(machine.control, Return)

    reference = machine.control.reference
    closure = machine.heap.get(reference).value

    assert isinstance(closure, Closure)
    assert closure.lambda_expression is expression
    assert closure.captured_locals.lookup("x") == (
        ImmediateInteger(10)
    )
    assert closure.required_slots == 2

    assert machine.heap.current_slots == 2
    assert machine.evaluator_transition_count == 1

    # The previous state must remain unchanged.
    assert original.machine_state.heap.current_slots == 0
    assert original.transition_index == 0


def test_variable_transition_preserves_local_reference():
    global_env = Environment({
        "x": ImmediateInteger(100),
    })

    local_env = global_env.extend({
        "x": ImmediateInteger(10),
    })

    original = make_state(CoreVar("x"))
    original = replace(
        original,
        machine_state=replace(
            original.machine_state,
            local_environment=local_env,
            global_environment=global_env,
        ),
    )

    transition = step(original, make_config())
    machine = transition.next_state.machine_state

    assert transition.rule_id == "CORE_EVAL_VARIABLE"
    assert machine.control == Return(ImmediateInteger(10))
    assert machine.heap.current_slots == 0
    assert machine.stack.depth == 0


def test_variable_transition_rejects_unknown_name():
    original = make_state(CoreVar("missing"))

    with pytest.raises(UnboundNameError):
        step(original, make_config())

    assert original.transition_index == 0
    assert original.machine_state.evaluator_transition_count == 0
    assert original.machine_state.heap.current_slots == 0


def test_core_application_pushes_function_continuation():
    function = CoreLam("x", CoreVar("x"))
    argument = CoreInt(5)
    expression = CoreApp(function, argument)

    original = make_state(expression)
    config = make_config()

    transition = step(original, config)
    machine = transition.next_state.machine_state

    assert transition.rule_id == "CORE_EVAL_APPLICATION"
    assert machine.control == EvaluateCore(function)

    assert machine.stack.depth == 1

    frame = machine.stack.peek()

    assert isinstance(frame, ApplyFunctionFrame)
    assert frame.argument is argument
    assert (
        frame.environment
        is original.machine_state.local_environment
    )

    # Only the function position was scheduled.
    assert machine.heap.current_slots == 0

    # The original execution state is unchanged.
    assert original.machine_state.stack.depth == 0
    assert original.transition_index == 0
    assert original.machine_state.evaluator_transition_count == 0

    assert transition.next_state.transition_index == 1
    assert machine.evaluator_transition_count == 1


def test_application_preserves_argument_call_site_environment():
    global_env = Environment({
        "x": ImmediateInteger(100),
    })

    local_env = global_env.extend({
        "x": ImmediateInteger(10),
    })

    expression = CoreApp(
        CoreLam("argument", CoreVar("argument")),
        CoreVar("x"),
    )

    original = make_state(expression)
    original = replace(
        original,
        machine_state=replace(
            original.machine_state,
            local_environment=local_env,
            global_environment=global_env,
        ),
    )

    transition = step(original, make_config())
    frame = transition.next_state.machine_state.stack.peek()

    assert isinstance(frame, ApplyFunctionFrame)
    assert frame.argument == CoreVar("x")
    assert frame.environment is local_env
    assert frame.environment.lookup("x") == ImmediateInteger(10)
    assert global_env.lookup("x") == ImmediateInteger(100)


def test_nested_applications_preserve_continuation_order():
    inner = CoreApp(
        CoreVar("f"),
        CoreInt(1),
    )

    outer = CoreApp(
        inner,
        CoreInt(2),
    )

    original = make_state(outer)
    config = make_config()

    first = step(original, config)
    second = step(first.next_state, config)

    machine = second.next_state.machine_state

    assert machine.control == EvaluateCore(CoreVar("f"))
    assert machine.stack.depth == 2

    outer_frame, inner_frame = machine.stack.frames

    assert isinstance(outer_frame, ApplyFunctionFrame)
    assert isinstance(inner_frame, ApplyFunctionFrame)

    assert outer_frame.argument == CoreInt(2)
    assert inner_frame.argument == CoreInt(1)

    # The inner application must be resumed first.
    assert machine.stack.peek() is inner_frame

    assert [
        first.rule_id,
        second.rule_id,
    ] == [
        "CORE_EVAL_APPLICATION",
        "CORE_EVAL_APPLICATION",
    ]

    assert original.machine_state.stack.depth == 0
    assert first.next_state.machine_state.stack.depth == 1
    assert second.next_state.machine_state.stack.depth == 2
