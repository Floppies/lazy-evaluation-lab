from dataclasses import replace

import pytest

from lazy_lab.core.nodes import (
    CoreApp,
    CoreBool,
    CoreInt,
    CoreLam,
    CoreVar,
    CorePrimOp,
    CoreIf,
)
from lazy_lab.engine.core_machine import (
    EvaluatorBudgetExhaustedError,
    InvalidMachineStateError,
    UnsupportedTransitionError,
    run_batch,
    step,
)
from lazy_lab.runtime.control import (
    EvaluateCore,
    Return,
    Force,
    ApplyPrimitive,
)
from lazy_lab.runtime.environment import Environment, UnboundNameError
from lazy_lab.runtime.heap import Heap, Indirection, Reserved
from lazy_lab.runtime.references import (
    ImmediateBoolean,
    ImmediateInteger,
    HeapReference,
)
from lazy_lab.runtime.stack import (
    Stack,
    ApplyFunctionFrame,
    PrimitiveOperandsFrame,
    IfFrame,
)
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


def test_forcing_immediate_returns_same_reference():
    original = make_state(CoreInt(0))
    reference = ImmediateInteger(42)

    original = replace(
        original,
        machine_state=replace(
            original.machine_state,
            control=Force(reference),
        ),
    )

    transition = step(original, make_config())
    machine = transition.next_state.machine_state

    assert transition.rule_id == "CORE_FORCE_IMMEDIATE"
    assert machine.control == Return(reference)
    assert machine.heap.current_slots == 0
    assert machine.stack.depth == 0
    assert original.machine_state.control == Force(reference)


def test_force_follows_indirection():
    original = make_state(CoreInt(0))
    heap = Heap()

    reference = heap.allocate(
        Indirection(ImmediateInteger(42)),
        allocated_slots=1,
    )

    original = replace(
        original,
        machine_state=replace(
            original.machine_state,
            heap=heap,
            control=Force(reference),
        ),
    )

    transition = step(original, make_config())
    machine = transition.next_state.machine_state

    assert transition.rule_id == "CORE_FORCE_INDIRECTION"
    assert machine.control == Force(ImmediateInteger(42))
    assert isinstance(
        machine.heap.get(reference).value,
        Indirection,
    )

    assert original.machine_state.heap.current_slots == 1
    assert original.transition_index == 0


def test_force_rejects_uninitialized_cell():
    original = make_state(CoreInt(0))
    heap = Heap()

    reference = heap.allocate(
        Reserved(),
        allocated_slots=1,
    )

    original = replace(
        original,
        machine_state=replace(
            original.machine_state,
            heap=heap,
            control=Force(reference),
        ),
    )

    with pytest.raises(
        InvalidMachineStateError,
        match="uninitialized",
    ):
        step(original, make_config())

    assert isinstance(heap.get(reference).value, Reserved)
    assert original.transition_index == 0


def test_primitive_starts_with_first_operand():
    expression = CorePrimOp(
        "+",
        (CoreInt(10), CoreInt(20)),
    )

    original = make_state(expression)
    transition = step(original, make_config())
    machine = transition.next_state.machine_state

    assert transition.rule_id == "CORE_EVAL_PRIMITIVE_START"
    assert machine.control == EvaluateCore(CoreInt(10))
    assert machine.stack.depth == 1

    frame = machine.stack.peek()

    assert isinstance(frame, PrimitiveOperandsFrame)
    assert frame.operator == "+"
    assert frame.remaining_arguments == (CoreInt(20),)
    assert frame.evaluated_arguments == ()
    assert frame.awaiting_whnf is False

    assert frame.environment is machine.local_environment
    assert machine.heap.current_slots == 0

    assert original.machine_state.stack.depth == 0
    assert original.transition_index == 0
    assert transition.next_state.transition_index == 1


def test_primitive_frame_preserves_lexical_environment():
    global_env = Environment({
        "x": ImmediateInteger(100),
    })

    local_env = global_env.extend({
        "x": ImmediateInteger(10),
    })

    expression = CorePrimOp(
        "+",
        (CoreVar("x"), CoreInt(2)),
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

    frame = machine.stack.peek()

    assert isinstance(frame, PrimitiveOperandsFrame)
    assert frame.environment is local_env
    assert frame.environment.lookup("x") == ImmediateInteger(10)
    assert machine.control == EvaluateCore(CoreVar("x"))


def test_unary_primitive_has_no_remaining_operands():
    expression = CorePrimOp(
        "negate",
        (CoreInt(5),),
    )

    transition = step(
        make_state(expression),
        make_config(),
    )

    machine = transition.next_state.machine_state
    frame = machine.stack.peek()

    assert isinstance(frame, PrimitiveOperandsFrame)
    assert frame.operator == "negate"
    assert frame.remaining_arguments == ()
    assert frame.evaluated_arguments == ()
    assert machine.control == EvaluateCore(CoreInt(5))


def test_empty_primitive_does_not_advance():
    expression = CorePrimOp("+", ())

    original = make_state(expression)

    with pytest.raises(
        InvalidMachineStateError,
        match="at least one operand",
    ):
        step(original, make_config())

    assert original.transition_index == 0
    assert original.machine_state.stack.depth == 0
    assert original.machine_state.heap.current_slots == 0


def test_primitive_operands_are_forced_left_to_right():
    original = make_state(
        CorePrimOp(
            "+",
            (CoreInt(10), CoreInt(20)),
        )
    )
    config = make_config()

    current = original
    rules = []

    for _ in range(9):
        transition = step(current, config)
        rules.append(transition.rule_id)
        current = transition.next_state

    machine = current.machine_state

    assert rules == [
        "CORE_EVAL_PRIMITIVE_START",
        "CORE_EVAL_INTEGER",
        "CORE_PRIM_REQUIRE_OPERAND_WHNF",
        "CORE_FORCE_IMMEDIATE",
        "CORE_PRIM_NEXT_OPERAND",
        "CORE_EVAL_INTEGER",
        "CORE_PRIM_REQUIRE_OPERAND_WHNF",
        "CORE_FORCE_IMMEDIATE",
        "CORE_PRIM_OPERANDS_READY",
    ]

    assert machine.control == ApplyPrimitive(
        "+",
        (
            ImmediateInteger(10),
            ImmediateInteger(20),
        ),
    )

    assert machine.stack.depth == 0
    assert machine.heap.current_slots == 0
    assert machine.evaluator_transition_count == 9

    # The initial state remains unchanged.
    assert original.transition_index == 0
    assert original.machine_state.stack.depth == 0

    transition = step(current, config)

    assert transition.rule_id == "CORE_PRIM_EXECUTE"
    assert transition.next_state.machine_state.control == Return(
        ImmediateInteger(30)
    )

    assert transition.next_state.machine_state.stack.depth == 0
    assert current.machine_state.control == ApplyPrimitive(
        "+",
        (
            ImmediateInteger(10),
            ImmediateInteger(20),
        ),
    )


def test_primitive_next_operand_uses_original_environment():
    global_env = Environment({
        "x": ImmediateInteger(100),
    })

    local_env = global_env.extend({
        "x": ImmediateInteger(10),
    })

    original = make_state(
        CorePrimOp(
            "+",
            (CoreInt(1), CoreVar("x")),
        )
    )
    original = replace(
        original,
        machine_state=replace(
            original.machine_state,
            global_environment=global_env,
            local_environment=local_env,
        ),
    )

    current = original
    rules = []

    for _ in range(5):
        transition = step(current, make_config())
        rules.append(transition.rule_id)
        current = transition.next_state

    machine = current.machine_state
    frame = machine.stack.peek()

    assert rules[-1] == "CORE_PRIM_NEXT_OPERAND"
    assert machine.control == EvaluateCore(CoreVar("x"))
    assert machine.local_environment is local_env

    assert isinstance(frame, PrimitiveOperandsFrame)
    assert frame.evaluated_arguments == (
        ImmediateInteger(1),
    )
    assert frame.remaining_arguments == ()
    assert frame.awaiting_whnf is False

    assert frame.environment is local_env
    assert frame.environment.lookup("x") == (
        ImmediateInteger(10)
    )


def test_primitive_operand_follows_indirection():
    heap = Heap()

    reference = heap.allocate(
        Indirection(ImmediateInteger(9)),
        allocated_slots=1,
    )

    environment = Environment({
        "x": reference,
    })

    original = make_state(
        CorePrimOp(
            "negate",
            (CoreVar("x"),),
        )
    )
    original = replace(
        original,
        machine_state=replace(
            original.machine_state,
            heap=heap,
            global_environment=environment,
            local_environment=environment,
        ),
    )

    current = original

    for _ in range(12):
        if isinstance(
            current.machine_state.control,
            ApplyPrimitive,
        ):
            break

        current = step(current, make_config()).next_state
    else:
        pytest.fail("Primitive operands never reached WHNF")

    machine = current.machine_state

    assert machine.control == ApplyPrimitive(
        "negate",
        (ImmediateInteger(9),),
    )

    # Forcing does not rewrite the indirection cell.
    assert machine.heap.get(reference).value == (
        Indirection(ImmediateInteger(9))
    )
    assert machine.stack.depth == 0


@pytest.mark.parametrize(
    "operator,arguments",
    [
        ("+", (ImmediateInteger(1),)),
        ("negate", (
            ImmediateInteger(1),
            ImmediateInteger(2),
        )),
        ("unknown", (ImmediateInteger(1),)),
    ],
)
def test_invalid_primitive_control_does_not_advance(
    operator,
    arguments,
):
    original = make_state(CoreInt(0))

    original = replace(
        original,
        machine_state=replace(
            original.machine_state,
            control=ApplyPrimitive(operator, arguments),
        ),
    )

    with pytest.raises(InvalidMachineStateError):
        step(original, make_config())

    assert original.transition_index == 0
    assert original.machine_state.stack.depth == 0
    assert original.machine_state.evaluator_transition_count == 0


def test_if_evaluates_condition_before_branches():
    expression = CoreIf(
        CoreBool(True),
        CoreInt(10),
        CoreInt(20),
    )

    original = make_state(expression)
    transition = step(original, make_config())
    machine = transition.next_state.machine_state

    assert transition.rule_id == "CORE_EVAL_IF_CONDITION"
    assert machine.control == EvaluateCore(CoreBool(True))
    assert machine.stack.depth == 1

    frame = machine.stack.peek()

    assert isinstance(frame, IfFrame)
    assert frame.then_branch is expression.then_branch
    assert frame.else_branch is expression.else_branch
    assert frame.awaiting_whnf is False
    assert frame.environment is original.machine_state.local_environment

    assert original.machine_state.stack.depth == 0
    assert original.transition_index == 0


@pytest.mark.parametrize(
    "condition,expected_branch,expected_rule",
    [
        (True, CoreInt(10), "CORE_IF_SELECT_THEN"),
        (False, CoreInt(20), "CORE_IF_SELECT_ELSE"),
    ],
)
def test_if_forces_condition_before_selecting_branch(
    condition,
    expected_branch,
    expected_rule,
):
    expression = CoreIf(
        CoreBool(condition),
        CoreInt(10),
        CoreInt(20),
    )

    current = make_state(expression)
    config = make_config()
    rules = []

    for _ in range(5):
        transition = step(current, config)
        rules.append(transition.rule_id)
        current = transition.next_state

    machine = current.machine_state

    assert rules == [
        "CORE_EVAL_IF_CONDITION",
        "CORE_EVAL_BOOLEAN",
        "CORE_IF_REQUIRE_CONDITION_WHNF",
        "CORE_FORCE_IMMEDIATE",
        expected_rule,
    ]

    assert machine.control == EvaluateCore(expected_branch)
    assert machine.stack.depth == 0
    assert machine.evaluator_transition_count == 5

