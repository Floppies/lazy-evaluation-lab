
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
from lazy_lab.runtime.control import (
    EvaluateCore,
    Return,
    ApplyPrimitive,
)
from lazy_lab.runtime.environment import Environment
from lazy_lab.runtime.heap import Heap, Indirection, Reserved
from lazy_lab.runtime.references import (
    ImmediateBoolean,
    ImmediateInteger,
)
from lazy_lab.runtime.stack import (
    Stack,
    ApplyFunctionFrame,
    RestoreEnvironmentFrame,
    ApplyArgumentFrame,
    PrimitiveOperandsFrame,
    GlobalDemandFrame,
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
from lazy_lab.runtime.transitions import BatchStopReason, RuleId
from lazy_lab.core.nodes import (
    CoreLam,
    CoreInt,
    CoreVar,
    CoreApp,
    CorePrimOp,
)
from lazy_lab.runtime.closures import (
    Closure,
    allocate_closure,
)
from lazy_lab.runtime.global_bindings import PendingGlobal
from lazy_lab.runtime.predefined import PredefinedFunction


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

    state = initial
    while state.machine_state.phase is ExecutionPhase.INITIALIZATION:
        state = step(state, config).next_state

    before = state.machine_state
    assert before.control == EvaluateCore(CoreVar("main"))
    main_reference = before.global_environment.lookup("main")
    answer_reference = before.global_environment.lookup("answer")

    # Inspect only the lookup transition, before root-result demand.
    transition = step(state, config)
    machine = transition.next_state.machine_state

    assert transition.rule_id == "CORE_EVAL_VARIABLE"
    assert machine.control == Return(main_reference)
    assert machine.control.reference is main_reference
    assert isinstance(
        machine.heap.get(main_reference).value,
        PendingGlobal,
    )
    assert isinstance(
        machine.heap.get(answer_reference).value,
        PendingGlobal,
    )

    for reference in (main_reference, answer_reference):
        assert machine.heap.get(reference) == before.heap.get(reference)
    assert machine.heap.next_object_id == before.heap.next_object_id
    assert machine.heap.current_slots == before.heap.current_slots
    assert machine.stack.depth == 0
    assert machine.evaluator_transition_count == before.evaluator_transition_count + 1
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


def test_global_alias_chain_reaches_whnf_without_updates():
    program = compile_source(
        "loop = loop\n"
        "answer = 42\n"
        "main = answer"
    )

    config = make_config()
    initial = create_initial_core_state(
        program,
        config,
        session_id="global-alias-demand",
    )

    result = run_batch(initial, config, max_steps=50)
    machine = result.state.machine_state

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert machine.control == Return(ImmediateInteger(42))
    assert machine.stack.depth == 0
    assert machine.local_environment is machine.global_environment

    # No global RHS was updated or memoized.
    for name in ("loop", "answer", "main"):
        reference = machine.global_environment.lookup(name)

        assert isinstance(
            machine.heap.get(reference).value,
            PendingGlobal,
        )

    assert any(
        entry.rule_id == "CORE_FORCE_GLOBAL_RHS"
        for entry in result.trace
    )
    assert any(
        entry.rule_id == "CORE_GLOBAL_DEMAND_RETURN"
        for entry in result.trace
    )

    # The first state remains unchanged.
    assert initial.transition_index == 0
    assert initial.machine_state.heap.current_slots == 0


def test_global_alias_to_function_reaches_whnf():
    program = compile_source(
        "identity x = x\n"
        "main = identity"
    )

    config = make_config()
    initial = create_initial_core_state(
        program,
        config,
        session_id="global-function-demand",
    )

    result = run_batch(initial, config, max_steps=50)
    machine = result.state.machine_state

    identity_reference = machine.global_environment.lookup(
        "identity"
    )

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert machine.control == Return(identity_reference)
    assert isinstance(
        machine.heap.get(identity_reference).value,
        Closure,
    )
    assert machine.stack.depth == 0


def test_recursive_global_demand_is_step_bounded():
    program = compile_source("main = main")

    config = replace(
        make_config(),
        execution_step_limit=20,
    )

    initial = create_initial_core_state(
        program,
        config,
        session_id="cyclic-global-demand",
    )

    result = run_batch(initial, config, max_steps=100)

    assert result.stop_reason is BatchStopReason.EVALUATOR_BUDGET
    assert (
        result.state.machine_state.evaluator_transition_count
        == 20
    )
    assert result.state.machine_state.status is ExecutionStatus.RUNNING


def test_cbv_identity_application_reaches_whnf():
    program = compile_source(
        "main = (\\x -> x) 5"
    )
    config = make_config(strategy=Strategy.CBV)

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbv-identity",
    )

    result = run_batch(initial, config, max_steps=80)
    machine = result.state.machine_state

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert machine.control == Return(ImmediateInteger(5))
    assert machine.stack.depth == 0
    assert machine.local_environment is machine.global_environment

    rules = [entry.rule_id for entry in result.trace]

    assert "CORE_APPLY_REQUIRE_FUNCTION_WHNF" in rules
    assert "CORE_CBV_EVAL_ARGUMENT" in rules
    assert "CORE_CBV_REQUIRE_ARGUMENT_WHNF" in rules
    assert "CORE_CBV_ENTER_BODY" in rules
    assert "CORE_RESTORE_CALLER_ENVIRONMENT" in rules

    assert initial.transition_index == 0
    assert initial.machine_state.heap.current_slots == 0


def test_cbv_applies_previously_installed_global_closure():
    program = compile_source(
        "identity x = x\n"
        "main = identity 7"
    )
    config = make_config(strategy=Strategy.CBV)

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbv-global-function",
    )

    result = run_batch(initial, config, max_steps=80)
    machine = result.state.machine_state

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert machine.control == Return(ImmediateInteger(7))
    assert machine.stack.depth == 0

    identity_ref = machine.global_environment.lookup(
        "identity"
    )

    assert isinstance(
        machine.heap.get(identity_ref).value,
        Closure,
    )


def test_cbv_nested_curried_application():
    program = compile_source(
        "main = (\\x -> \\y -> x) 10 20"
    )
    config = make_config(strategy=Strategy.CBV)

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbv-curried",
    )

    result = run_batch(initial, config, max_steps=120)
    machine = result.state.machine_state

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert machine.control == Return(ImmediateInteger(10))
    assert machine.stack.depth == 0
    assert machine.local_environment is machine.global_environment

    # One closure for each evaluated lambda.
    closures = [
        cell.value
        for cell in machine.heap.cells.values()
        if isinstance(cell.value, Closure)
    ]

    assert len(closures) == 2
    assert sorted(c.required_slots for c in closures) == [1, 2]


def test_cbv_does_not_skip_unused_diverging_argument():
    program = compile_source(
        "loop = loop\n"
        "main = (\\x -> 42) loop"
    )
    config = replace(
        make_config(strategy=Strategy.CBV),
        execution_step_limit=35,
    )

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbv-strictness",
    )

    result = run_batch(initial, config, max_steps=100)

    assert result.stop_reason is BatchStopReason.EVALUATOR_BUDGET
    assert result.state.machine_state.status is ExecutionStatus.RUNNING

    assert "CORE_CBV_EVAL_ARGUMENT" in [
        entry.rule_id for entry in result.trace
    ]

    assert "CORE_CBV_ENTER_BODY" not in [
        entry.rule_id for entry in result.trace
    ]


def test_cbv_restores_call_site_environment():
    program = compile_source("")
    config = make_config(strategy=Strategy.CBV)

    expression = CoreApp(
        CoreLam("x", CoreVar("x")),
        CoreInt(5),
    )

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbv-environment",
        entry=expression,
    )

    result = run_batch(initial, config, max_steps=80)
    machine = result.state.machine_state

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert machine.control == Return(ImmediateInteger(5))
    assert machine.local_environment is machine.global_environment
    assert machine.stack.depth == 0


def test_restore_environment_frame_preserves_lexical_identity():
    environment = Environment({
        "x": ImmediateInteger(42),
    })

    frame = RestoreEnvironmentFrame(environment)

    assert frame.environment is environment

    stack = Stack()
    stack.push(frame)

    snapshot = stack.clone()

    assert snapshot.peek() is frame
    assert stack.pop() is frame
    assert snapshot.depth == 1


def test_cbv_nested_application_preserves_lexical_capture():
    program = compile_source(
        "x = 99\n"
        "main = (\\x -> (\\y -> x) 20) 10"
    )

    config = make_config(strategy=Strategy.CBV)

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbv-lexical-capture",
    )

    result = run_batch(initial, config, max_steps=100)
    machine = result.state.machine_state

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert machine.control == Return(ImmediateInteger(10))
    assert machine.stack.depth == 0
    assert machine.local_environment is machine.global_environment

    # The global binding x must not be changed.
    global_x = machine.global_environment.lookup("x")

    assert isinstance(
        machine.heap.get(global_x).value,
        PendingGlobal,
    )

    closures = [
        cell.value
        for cell in machine.heap.cells.values()
        if isinstance(cell.value, Closure)
    ]

    assert len(closures) == 2
    assert sorted(c.required_slots for c in closures) == [1, 2]

    captured = [
        closure
        for closure in closures
        if "x" in closure.captured_locals.bindings
    ]

    assert len(captured) == 1
    assert captured[0].captured_locals.lookup("x") == (
        ImmediateInteger(10)
    )


def test_cbv_global_function_uses_argument_call_site_scope():
    program = compile_source(
        "identity y = y\n"
        "main = (\\x -> identity x) 17"
    )

    config = make_config(strategy=Strategy.CBV)

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbv-call-site",
    )

    result = run_batch(initial, config, max_steps=100)
    machine = result.state.machine_state

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert machine.control == Return(ImmediateInteger(17))
    assert machine.stack.depth == 0
    assert machine.local_environment is machine.global_environment

    rules = [entry.rule_id for entry in result.trace]

    assert rules.count("CORE_CBV_ENTER_BODY") == 2
    assert rules.count("CORE_CBV_EVAL_ARGUMENT") == 2


def test_cbv_applies_function_through_global_alias():
    program = compile_source(
        "identity x = x\n"
        "alias = identity\n"
        "main = alias 23"
    )

    config = make_config(strategy=Strategy.CBV)

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbv-global-alias",
    )

    result = run_batch(initial, config, max_steps=100)
    machine = result.state.machine_state

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert machine.control == Return(ImmediateInteger(23))
    assert machine.stack.depth == 0

    alias_reference = machine.global_environment.lookup(
        "alias"
    )

    assert isinstance(
        machine.heap.get(alias_reference).value,
        PendingGlobal,
    )

    rules = [entry.rule_id for entry in result.trace]

    assert "CORE_FORCE_GLOBAL_RHS" in rules
    assert "CORE_CBV_ENTER_BODY" in rules


def test_cbv_enter_body_preserves_previous_snapshot():
    program = compile_source(
        "main = (\\x -> x) 9"
    )
    config = make_config(strategy=Strategy.CBV)

    state = create_initial_core_state(
        program,
        config,
        session_id="cbv-body-snapshot",
    )

    # Advance until the machine enters the closure body.
    for _ in range(60):
        transition = step(state, config)

        if transition.rule_id == "CORE_CBV_ENTER_BODY":
            break

        state = transition.next_state
    else:
        pytest.fail("CBV never entered the function body")

    previous = state
    successor = transition.next_state

    before = previous.machine_state
    after = successor.machine_state

    assert isinstance(
        before.stack.peek(),
        ApplyArgumentFrame,
    )
    assert isinstance(
        after.stack.peek(),
        RestoreEnvironmentFrame,
    )

    assert before.local_environment is (
        before.global_environment
    )

    assert after.local_environment.lookup("x") == (
        ImmediateInteger(9)
    )

    assert before.heap is not after.heap
    assert before.stack is not after.stack
    assert before.stack.depth == after.stack.depth

    # Running the successor must not modify the previous state.
    result = run_batch(
        successor,
        config,
        max_steps=60,
    )

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert result.state.machine_state.control == Return(
        ImmediateInteger(9)
    )

    assert isinstance(
        previous.machine_state.stack.peek(),
        ApplyArgumentFrame,
    )
    assert previous.transition_index == state.transition_index


def test_cbv_rejects_application_of_non_function():
    program = compile_source("")
    config = make_config(strategy=Strategy.CBV)

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbv-invalid-function",
        entry=CoreApp(CoreInt(1), CoreInt(2)),
    )

    with pytest.raises(
        TypeError,
        match="Cannot apply a non-function value",
    ):
        run_batch(initial, config, max_steps=40)

    assert initial.transition_index == 0
    assert initial.machine_state.stack.depth == 0
    assert initial.machine_state.heap.current_slots == 0


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBN, Strategy.CBNEED],
)
def test_non_strict_application_remains_explicitly_unsupported(
    strategy,
):
    program = compile_source(
        "main = (\\x -> x) 5"
    )
    config = make_config(strategy=strategy)

    initial = create_initial_core_state(
        program,
        config,
        session_id="non-strict-boundary",
    )

    with pytest.raises(
        UnsupportedTransitionError,
        match="Non-strict application",
    ):
        run_batch(initial, config, max_steps=40)


def test_cbv_trace_modes_have_equivalent_machine_results():
    program = compile_source(
        "main = (\\x -> \\y -> x) 10 20"
    )

    full_config = make_config(
        strategy=Strategy.CBV,
        trace_mode=TraceMode.FULL,
    )

    metrics_config = make_config(
        strategy=Strategy.CBV,
        trace_mode=TraceMode.METRICS_ONLY,
    )

    initial = create_initial_core_state(
        program,
        full_config,
        session_id="cbv-trace-equivalence",
    )

    full = run_batch(initial, full_config, max_steps=100)
    metrics = run_batch(initial, metrics_config, max_steps=100)

    assert full.stop_reason == metrics.stop_reason
    assert full.stop_reason is BatchStopReason.WHNF_PENDING

    left = full.state.machine_state
    right = metrics.state.machine_state

    assert left.control == right.control
    assert left.control == Return(ImmediateInteger(10))

    assert left.stack.depth == right.stack.depth == 0
    assert left.heap.current_slots == right.heap.current_slots
    assert left.heap.next_object_id == right.heap.next_object_id

    assert (
        left.evaluator_transition_count
        == right.evaluator_transition_count
    )
    assert full.state.transition_index == metrics.state.transition_index

    assert len(full.trace) > 0
    assert metrics.trace == ()


def test_compiled_primitive_starts_left_to_right_evaluation():
    program = compile_source(
        "main = 1 + 2 * 3"
    )
    config = make_config(strategy=Strategy.CBV)

    initial = create_initial_core_state(
        program,
        config,
        session_id="primitive-start",
    )

    current = initial

    for _ in range(30):
        transition = step(current, config)
        current = transition.next_state

        if transition.rule_id == "CORE_EVAL_PRIMITIVE_START":
            break
    else:
        pytest.fail("Primitive evaluation never started")

    machine = current.machine_state
    frame = machine.stack.peek()

    assert machine.control == EvaluateCore(CoreInt(1))
    assert isinstance(frame, PrimitiveOperandsFrame)
    assert frame.operator == "+"
    assert len(frame.remaining_arguments) == 1

    # Precedence was preserved by the compiler.
    assert frame.remaining_arguments[0] == CorePrimOp(
        "*",
        (CoreInt(2), CoreInt(3)),
    )

    assert frame.evaluated_arguments == ()
    assert machine.status is ExecutionStatus.RUNNING


def test_primitive_forces_global_operand_without_memoization():
    program = compile_source(
        "answer = 40\n"
        "main = answer + 2"
    )
    config = make_config(strategy=Strategy.CBV)

    initial = create_initial_core_state(
        program,
        config,
        session_id="primitive-global-operand",
    )

    current = initial
    rules = []

    for _ in range(80):
        if isinstance(
            current.machine_state.control,
            ApplyPrimitive,
        ):
            break

        transition = step(current, config)
        rules.append(transition.rule_id)
        current = transition.next_state
    else:
        pytest.fail("Primitive operands never became ready")

    machine = current.machine_state

    assert machine.control == ApplyPrimitive(
        "+",
        (
            ImmediateInteger(40),
            ImmediateInteger(2),
        ),
    )

    assert rules.count("CORE_PRIM_REQUIRE_OPERAND_WHNF") == 2
    assert rules.count("CORE_PRIM_NEXT_OPERAND") == 1
    assert "CORE_FORCE_GLOBAL_RHS" in rules

    # Both globals remain pending: no sharing updates yet.
    for name in ("answer", "main"):
        reference = machine.global_environment.lookup(name)

        assert isinstance(
            machine.heap.get(reference).value,
            PendingGlobal,
        )

    # The pending main RHS still owns the enclosing
    # global-demand continuation until the + is executed.
    assert machine.stack.depth == 1
    assert isinstance(
        machine.stack.peek(),
        GlobalDemandFrame,
    )

    assert initial.transition_index == 0
    assert initial.machine_state.heap.current_slots == 0


@pytest.mark.parametrize(
    "source,expected",
    [
        ("main = 1 + 2 * 3", ImmediateInteger(7)),
        ("main = (1 + 2) * 3", ImmediateInteger(9)),
        ("main = 10 - 15", ImmediateInteger(-5)),
        ("main = -5", ImmediateInteger(-5)),
        ("main = 10 * -3", ImmediateInteger(-30)),
        ("main = 3 < 5", ImmediateBoolean(True)),
        ("main = 3 <= 3", ImmediateBoolean(True)),
        ("main = 3 > 5", ImmediateBoolean(False)),
        ("main = 5 >= 5", ImmediateBoolean(True)),
        ("main = 4 == 4", ImmediateBoolean(True)),
        ("main = 4 != 4", ImmediateBoolean(False)),
        ("main = True == False", ImmediateBoolean(False)),
        ("main = True != False", ImmediateBoolean(True)),
    ],
)
def test_primitive_operations_produce_expected_whnf(
    source,
    expected,
):
    config = make_config(strategy=Strategy.CBV)
    program = compile_source(source)

    initial = create_initial_core_state(
        program,
        config,
        session_id="primitive-evaluation",
    )

    result = run_batch(initial, config, max_steps=150)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert result.state.machine_state.control == Return(expected)
    assert result.state.machine_state.stack.depth == 0

    assert any(
        entry.rule_id == "CORE_PRIM_EXECUTE"
        for entry in result.trace
    )


def test_cbv_function_accepts_primitive_argument():
    program = compile_source(
        "double x = x * 2\n"
        "main = double (3 + 4)"
    )

    config = make_config(strategy=Strategy.CBV)

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbv-primitive-argument",
    )

    result = run_batch(initial, config, max_steps=150)
    machine = result.state.machine_state

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert machine.control == Return(ImmediateInteger(14))
    assert machine.stack.depth == 0

    rules = [entry.rule_id for entry in result.trace]

    assert rules.count("CORE_PRIM_EXECUTE") == 2
    assert "CORE_CBV_ENTER_BODY" in rules


@pytest.mark.parametrize(
    "source",
    [
        "main = True + 1",
        "main = -False",
        "main = True < False",
        "main = 1 == True",
    ],
)
def test_primitives_reject_invalid_operand_types(source):
    program = compile_source(source)
    config = make_config(strategy=Strategy.CBV)

    initial = create_initial_core_state(
        program,
        config,
        session_id="primitive-type-error",
    )

    with pytest.raises(TypeError):
        run_batch(initial, config, max_steps=100)

    assert initial.transition_index == 0
    assert initial.machine_state.heap.current_slots == 0


@pytest.mark.parametrize("strategy", list(Strategy))
@pytest.mark.parametrize(
    "source,expected,selection_rule",
    [
        (
            "loop = loop\n"
            "main = if True then 42 else loop",
            42,
            "CORE_IF_SELECT_THEN",
        ),
        (
            "loop = loop\n"
            "main = if False then loop else 7",
            7,
            "CORE_IF_SELECT_ELSE",
        ),
    ],
)
def test_if_evaluates_only_selected_branch(
    strategy,
    source,
    expected,
    selection_rule,
):
    program = compile_source(source)
    config = make_config(strategy=strategy)

    initial = create_initial_core_state(
        program,
        config,
        session_id="conditional-branch",
    )

    result = run_batch(initial, config, max_steps=100)
    machine = result.state.machine_state

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert machine.control == Return(
        ImmediateInteger(expected)
    )
    assert machine.stack.depth == 0

    rules = [entry.rule_id for entry in result.trace]

    assert selection_rule in rules
    assert "CORE_IF_REQUIRE_CONDITION_WHNF" in rules

    # The discarded recursive branch was never demanded.
    loop_reference = machine.global_environment.lookup("loop")

    assert isinstance(
        machine.heap.get(loop_reference).value,
        PendingGlobal,
    )


def test_if_with_primitive_condition_and_branch():
    program = compile_source(
        "main = if 2 > 1 then 40 + 2 else 0"
    )

    config = make_config(strategy=Strategy.CBV)

    initial = create_initial_core_state(
        program,
        config,
        session_id="conditional-primitive",
    )

    result = run_batch(initial, config, max_steps=150)
    machine = result.state.machine_state

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert machine.control == Return(ImmediateInteger(42))

    rules = [entry.rule_id for entry in result.trace]

    assert rules.count("CORE_PRIM_EXECUTE") == 2
    assert "CORE_IF_SELECT_THEN" in rules
    assert "CORE_IF_SELECT_ELSE" not in rules


def test_if_rejects_non_boolean_condition():
    program = compile_source(
        "main = if 1 then 2 else 3"
    )

    config = make_config(strategy=Strategy.CBV)

    initial = create_initial_core_state(
        program,
        config,
        session_id="invalid-if-condition",
    )

    with pytest.raises(
        TypeError,
        match="Boolean",
    ):
        run_batch(initial, config, max_steps=100)

    assert initial.transition_index == 0
    assert initial.machine_state.stack.depth == 0
    assert initial.machine_state.heap.current_slots == 0


def test_primitive_conditional_trace_modes_are_equivalent():
    program = compile_source(
        "base = 6\n"
        "main = if base >= 5 then base * 7 else 0"
    )

    results = {}

    for mode in TraceMode:
        config = make_config(
            strategy=Strategy.CBV,
            trace_mode=mode,
        )

        initial = create_initial_core_state(
            program,
            config,
            session_id="trace-audit",
        )

        results[mode] = run_batch(
            initial,
            config,
            max_steps=100,
        )

    full = results[TraceMode.FULL]
    events = results[TraceMode.EVENTS]
    metrics = results[TraceMode.METRICS_ONLY]

    for result in results.values():
        machine = result.state.machine_state

        assert result.stop_reason is BatchStopReason.WHNF_PENDING
        assert machine.control == Return(ImmediateInteger(42))
        assert machine.stack.depth == 0
        assert machine.local_environment is machine.global_environment

    full_machine = full.state.machine_state

    for result in (events, metrics):
        machine = result.state.machine_state

        assert (
            result.state.transition_index
            == full.state.transition_index
        )
        assert (
            machine.evaluator_transition_count
            == full_machine.evaluator_transition_count
        )
        assert machine.heap.current_slots == full_machine.heap.current_slots
        assert machine.heap.next_object_id == full_machine.heap.next_object_id
        assert machine.heap.cells.keys() == full_machine.heap.cells.keys()

        # Independent runs create distinct identity-based heap payloads.
        for object_id, cell in machine.heap.cells.items():
            full_cell = full_machine.heap.cells[object_id]

            assert cell.object_id == full_cell.object_id
            assert cell.allocated_slots == full_cell.allocated_slots
            assert type(cell.value) is type(full_cell.value)

            if isinstance(cell.value, PredefinedFunction):
                assert isinstance(full_cell.value, PredefinedFunction)
                assert cell.value.name == full_cell.value.name
            else:
                assert isinstance(cell.value, PendingGlobal)
                assert isinstance(full_cell.value, PendingGlobal)
                # All runs use the same compiled, immutable Core program.
                assert cell.value.expression is full_cell.value.expression

    # Currently FULL and EVENTS record the same basic trace entries.
    assert full.trace == events.trace
    assert metrics.trace == ()

    assert len(full.trace) == full.state.transition_index

    assert all(
        isinstance(entry.rule_id, RuleId)
        for entry in full.trace
    )

    assert [
        entry.previous_state_id
        for entry in full.trace
    ] == list(range(len(full.trace)))

    assert [
        entry.next_state_id
        for entry in full.trace
    ] == list(range(1, len(full.trace) + 1))


def test_conditional_can_resume_after_evaluator_budget():
    program = compile_source(
        "main = if 2 < 3 then 42 else 0"
    )

    full_config = make_config(strategy=Strategy.CBV)

    limited_config = replace(
        full_config,
        execution_step_limit=10,
    )

    initial = create_initial_core_state(
        program,
        limited_config,
        session_id="conditional-resume",
    )

    # Stop in the middle of evaluating the condition.
    partial = run_batch(
        initial,
        limited_config,
        max_steps=100,
    )

    paused = partial.state
    paused_machine = paused.machine_state

    assert partial.stop_reason is BatchStopReason.EVALUATOR_BUDGET
    assert paused_machine.evaluator_transition_count == 10
    assert paused_machine.status is ExecutionStatus.RUNNING
    assert paused_machine.stack.depth > 0

    # Resume the same execution with a larger budget.
    resumed = run_batch(
        paused,
        full_config,
        max_steps=100,
    )

    assert resumed.stop_reason is BatchStopReason.WHNF_PENDING
    assert resumed.state.machine_state.control == Return(
        ImmediateInteger(42)
    )
    assert resumed.state.machine_state.stack.depth == 0

    # Compare with an uninterrupted execution.
    uninterrupted = run_batch(
        initial,
        full_config,
        max_steps=100,
    )

    assert uninterrupted.stop_reason is BatchStopReason.WHNF_PENDING
    assert (
        resumed.state.transition_index
        == uninterrupted.state.transition_index
    )
    assert partial.trace + resumed.trace == uninterrupted.trace

    # Resuming must not mutate the paused snapshot.
    assert paused.transition_index == 10
    assert paused.machine_state.stack.depth > 0
    assert initial.transition_index == 0
