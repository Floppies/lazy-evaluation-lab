
"""B02-to-B03 integration tests for the limited Core runtime."""

from dataclasses import replace

import pytest

from lazy_lab.pipeline import compile_source
from lazy_lab.engine.core_machine import (
    UnsupportedTransitionError,
    run_batch,
    step,
    create_initial_core_state,
)
from lazy_lab.runtime.control import EvaluateCore, Return
from lazy_lab.runtime.environment import Environment
from lazy_lab.runtime.heap import Heap, Indirection, Reserved
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
from lazy_lab.runtime.transitions import BatchStopReason
from lazy_lab.core.nodes import CoreLam, CoreInt
from lazy_lab.runtime.closures import (
    Closure,
    allocate_closure,
)
from lazy_lab.runtime.global_bindings import PendingGlobal


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

def test_mismatched_strategy_is_rejected():
    state = make_demo_state(
        "main = 42",
        strategy=Strategy.CBNEED,
    )

    config = make_config(strategy=Strategy.CBV)

    with pytest.raises(ValueError):
        step(state, config)
#TODO This test should be removed or changed when stg is implemented
def test_stg_execution_is_not_yet_implemented():
    state = make_demo_state("main = 42")

    stg_machine = replace(
        state.machine_state,
        machine_kind=MachineKind.STG,
    )

    stg_state = replace(
        state,
        machine_state=stg_machine,
    )

    stg_config = replace(
        make_config(),
        machine_kind=MachineKind.STG,
    )

    with pytest.raises(UnsupportedTransitionError):
        step(stg_state, stg_config)

def test_compiled_nested_lambdas_capture_outer_argument():
    program = compile_source(
        "global_value = 100\n"
        "main = \\x -> \\y -> global_value + x + y"
    )

    outer_expression = program.bindings[1].rhs
    assert isinstance(outer_expression, CoreLam)

    global_env = Environment({
        "global_value": ImmediateInteger(100),
    })
    heap = Heap()

    # Build the outer function without evaluating its body.
    outer_ref = allocate_closure(
        heap,
        outer_expression,
        global_env,
        global_env,
    )

    outer_closure = heap.get(outer_ref).value

    assert isinstance(outer_closure, Closure)
    assert outer_closure.captured_locals.bindings == {}
    assert outer_closure.required_slots == 1

    # Simulate lexical parameter binding for the outer call.
    outer_call_env = outer_closure.call_environment(
        ImmediateInteger(10),
        global_env,
    )

    inner_expression = outer_expression.body
    assert isinstance(inner_expression, CoreLam)

    # The inner lambda must capture x from its definition site.
    inner_ref = allocate_closure(
        heap,
        inner_expression,
        outer_call_env,
        global_env,
    )

    inner_closure = heap.get(inner_ref).value

    assert isinstance(inner_closure, Closure)
    assert set(inner_closure.captured_locals.bindings) == {"x"}
    assert inner_closure.captured_locals.lookup("x") == (
        ImmediateInteger(10)
    )
    assert inner_closure.required_slots == 2

    inner_call_env = inner_closure.call_environment(
        ImmediateInteger(7),
        global_env,
    )

    assert inner_call_env.lookup("global_value") == (
        ImmediateInteger(100)
    )
    assert inner_call_env.lookup("x") == ImmediateInteger(10)
    assert inner_call_env.lookup("y") == ImmediateInteger(7)

    assert heap.current_slots == 3
    assert heap.next_object_id == 2

def test_compiled_nested_closure_preserves_local_shadowing():
    program = compile_source(
        "x = 100\n"
        "main = \\x -> \\y -> x"
    )

    outer_expression = program.bindings[1].rhs
    assert isinstance(outer_expression, CoreLam)

    global_env = Environment({
        "x": ImmediateInteger(100),
    })
    heap = Heap()

    outer_ref = allocate_closure(
        heap,
        outer_expression,
        global_env,
        global_env,
    )
    outer_closure = heap.get(outer_ref).value

    assert isinstance(outer_closure, Closure)

    # The outer parameter shadows global x.
    outer_call_env = outer_closure.call_environment(
        ImmediateInteger(10),
        global_env,
    )

    inner_expression = outer_expression.body
    assert isinstance(inner_expression, CoreLam)

    inner_ref = allocate_closure(
        heap,
        inner_expression,
        outer_call_env,
        global_env,
    )
    inner_closure = heap.get(inner_ref).value

    assert isinstance(inner_closure, Closure)
    assert inner_closure.captured_locals.lookup("x") == (
        ImmediateInteger(10)
    )

    inner_call_env = inner_closure.call_environment(
        ImmediateInteger(20),
        global_env,
    )

    assert inner_call_env.lookup("x") == ImmediateInteger(10)
    assert inner_call_env.lookup("y") == ImmediateInteger(20)
    assert global_env.lookup("x") == ImmediateInteger(100)


def test_global_variable_lookup_does_not_force_rhs():
    program = compile_source(
        "answer = 42\n"
        "main = answer"
    )
    config = make_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="global-lookup",
    )

    result = run_batch(initial, config, max_steps=20)
    machine = result.state.machine_state

    main_reference = machine.global_environment.lookup("main")
    answer_reference = machine.global_environment.lookup("answer")

    assert machine.control == Return(main_reference)
    assert isinstance(
        machine.heap.get(main_reference).value,
        PendingGlobal,
    )
    assert isinstance(
        machine.heap.get(answer_reference).value,
        PendingGlobal,
    )

    assert result.trace[-1].rule_id == "CORE_EVAL_VARIABLE"
    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert machine.status is ExecutionStatus.RUNNING


def test_global_lambda_lookup_reuses_installed_closure():
    program = compile_source(
        "identity x = x\n"
        "main = identity"
    )
    config = make_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="global-closure",
        entry="identity",
    )

    result = run_batch(initial, config, max_steps=20)
    machine = result.state.machine_state

    reference = machine.global_environment.lookup("identity")

    assert machine.control == Return(reference)
    assert isinstance(machine.heap.get(reference).value, Closure)

    # One predefined function and two global bindings.
    # CoreVar lookup must not allocate another closure.
    assert machine.heap.next_object_id == 3
    assert machine.heap.current_slots == 3

    assert result.trace[-1].rule_id == "CORE_EVAL_VARIABLE"


def test_compiled_application_preserves_pending_function_frame():
    state = make_demo_state(
        "main = (\\x -> x) 5"
    )
    config = make_config()

    result = run_batch(
        state,
        config,
        max_steps=2,
    )

    machine = result.state.machine_state

    assert [
        entry.rule_id for entry in result.trace
    ] == [
        "CORE_EVAL_APPLICATION",
        "CORE_EVAL_LAMBDA",
    ]

    assert isinstance(machine.control, Return)
    assert machine.stack.depth == 1

    frame = machine.stack.peek()
    assert isinstance(frame, ApplyFunctionFrame)
    assert frame.argument == CoreInt(5)

    closure_reference = machine.control.reference
    closure = machine.heap.get(closure_reference).value

    assert isinstance(closure, Closure)
    assert closure.lambda_expression.parameter == "x"

    # Evaluation is suspended before continuation handling.
    assert machine.status is ExecutionStatus.RUNNING
    assert result.stop_reason is BatchStopReason.BATCH_LIMIT
    assert result.state.transition_index == 2

    assert state.transition_index == 0
    assert state.machine_state.stack.depth == 0
    assert state.machine_state.heap.current_slots == 0
