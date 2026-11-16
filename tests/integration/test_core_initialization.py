import pytest

from dataclasses import replace

from lazy_lab.core.nodes import CoreBinding, CoreInt
from lazy_lab.engine import core_machine
from lazy_lab.engine.core_machine import (
    _reserve_global_scope,
    _install_global_rhs,
    step,
    run_batch,
    BatchStopReason,
    EvaluatorBudgetExhaustedError,
    UninitializedLocalBindingError,
)
from lazy_lab.metrics.effects import HeapAllocated, HeapBaselineRecorded
from lazy_lab.metrics.events import SemanticEventKind
from lazy_lab.metrics.reducer import reduce_metrics
from lazy_lab.metrics.state import InstrumentationState
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.environment import (
    UnboundNameError,
)
from lazy_lab.runtime.heap import Heap, Reserved, Indirection
from lazy_lab.runtime.stack import (
    RestoreEnvironmentFrame,
    LocalValueInitializationFrame
)
from lazy_lab.runtime.predefined import PredefinedFunction
from lazy_lab.runtime.references import HeapReference, ImmediateInteger
from lazy_lab.runtime.transitions import RuleId
from lazy_lab.core.nodes import CoreInt, CoreVar, CoreLetRec
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionPhase,
    ExecutionStatus,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.engine.core_machine import (
    UnsupportedTransitionError,
    create_initial_core_state,
    InvalidMachineStateError
)
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.control import (
    InitializeCoreBindings,
    EvaluateCore,
    Return,
    InitializeLocalBindings,
    Force,
)
from lazy_lab.runtime.global_bindings import PendingGlobal
from lazy_lab.runtime.thunks import PendingThunk, ThunkPayload
from lazy_lab.runtime.predefined import PredefinedFunction
from lazy_lab.runtime.closures import Closure

def make_config(strategy=Strategy.CBNEED):
    return ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=strategy,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=100,
        result_node_limit=100,
        trace_mode=TraceMode.FULL,
    )

def test_every_global_receives_a_stable_address():
    program = compile_source(
        "first = second\n"
        "second = 42\n"
        "main = first"
    )

    heap = Heap()
    environment = _reserve_global_scope(
        heap,
        program.bindings,
    )

    assert set(environment.bindings) == {
        "first", "second", "main"
    }

    references = [
        environment.lookup(name)
        for name in ("first", "second", "main")
    ]

    assert all(
        isinstance(reference, HeapReference)
        for reference in references
    )

    assert len(set(references)) == 3

    assert all(
        isinstance(heap.get(reference).value, Reserved)
        for reference in references
    )


def test_global_rhs_is_not_evaluated():
    program = compile_source(
        "loop = loop\n"
        "main = 42"
    )

    heap = Heap()
    environment = _reserve_global_scope(
        heap,
        program.bindings,
    )

    assert isinstance(
        heap.get(environment.lookup("loop")).value,
        Reserved,
    )

    assert isinstance(
        heap.get(environment.lookup("main")).value,
        Reserved,
    )


def test_predefined_function_is_in_outer_scope():
    program = compile_source("main = seq 1 2")

    heap = Heap()
    environment = _reserve_global_scope(
        heap,
        program.bindings,
    )

    assert "seq" not in environment.bindings
    assert environment.parent is not None

    reference = environment.lookup("seq")
    builtin = heap.get(reference).value

    assert isinstance(builtin, PredefinedFunction)
    assert builtin.name == "seq"
    assert builtin.arity == 2
    assert builtin.required_slots == 1


def test_user_global_shadows_predefined_seq():
    program = compile_source(
        "seq x y = x\n"
        "main = seq 1 2"
    )

    heap = Heap()
    environment = _reserve_global_scope(
        heap,
        program.bindings,
    )

    global_reference = environment.lookup("seq")
    predefined_reference = environment.parent.lookup("seq")

    assert global_reference != predefined_reference
    assert isinstance(
        heap.get(global_reference).value,
        Reserved,
    )
    assert isinstance(
        heap.get(predefined_reference).value,
        PredefinedFunction,
    )


def test_reservation_uses_exact_abstract_slots():
    program = compile_source(
        "a = 1\n"
        "b = 2\n"
        "main = a"
    )

    heap = Heap()
    environment = _reserve_global_scope(
        heap,
        program.bindings,
    )

    assert len(environment.bindings) == 3
    assert heap.current_slots == 4
    assert heap.next_object_id == 4


def test_missing_name_still_raises():
    program = compile_source("main = 42")

    heap = Heap()
    environment = _reserve_global_scope(
        heap,
        program.bindings,
    )

    with pytest.raises(UnboundNameError):
        environment.lookup("missing")


def test_duplicate_globals_are_rejected_before_allocation():
    bindings = (
        CoreBinding("x", CoreInt(1)),
        CoreBinding("x", CoreInt(2)),
    )

    heap = Heap()

    with pytest.raises(ValueError, match="Duplicate"):
        _reserve_global_scope(heap, bindings)

    assert heap.current_slots == 0

@pytest.mark.parametrize("strategy", list(Strategy))
def test_initial_state_preserves_strategy(strategy):
    program = compile_source("main = 42")
    state = create_initial_core_state(
        program,
        make_config(strategy),
        session_id="test-session",
    )

    machine = state.machine_state

    assert machine.strategy is strategy
    assert machine.phase is ExecutionPhase.INITIALIZATION
    assert machine.status is ExecutionStatus.RUNNING
    assert state.state_id == 0
    assert state.transition_index == 0
    assert machine.evaluator_transition_count == 0


def test_initial_control_retains_program_and_entry():
    program = compile_source(
        "loop = loop\n"
        "main = 42"
    )
    state = create_initial_core_state(
        program,
        make_config(),
        session_id="entry-test",
    )

    control = state.machine_state.control

    assert isinstance(control, InitializeCoreBindings)
    assert control.bindings == program.bindings
    assert control.next_index == 0
    assert control.entry_expression == CoreVar("main")


def test_initialization_does_not_evaluate_global_rhs():
    program = compile_source(
        "loop = loop\n"
        "main = 42"
    )
    state = create_initial_core_state(
        program,
        make_config(),
        session_id="lazy-globals",
    )

    machine = state.machine_state

    assert machine.heap.current_slots == 0
    assert machine.heap.next_object_id == 0
    assert machine.stack.depth == 0
    assert machine.global_environment.bindings == {}
    assert machine.evaluator_transition_count == 0


def test_explicit_global_entry_without_main():
    program = compile_source("answer = 7")
    state = create_initial_core_state(
        program,
        make_config(),
        session_id="named-entry",
        entry="answer",
    )

    assert (
        state.machine_state.control.entry_expression
        == CoreVar("answer")
    )


def test_explicit_core_expression_without_main():
    program = compile_source("answer = 7")
    expression = CoreInt(9)

    state = create_initial_core_state(
        program,
        make_config(),
        session_id="expression-entry",
        entry=expression,
    )

    assert (
        state.machine_state.control.entry_expression
        is expression
    )


def test_missing_default_main_is_rejected():
    program = compile_source("answer = 7")

    with pytest.raises(ValueError, match="main"):
        create_initial_core_state(
            program,
            make_config(),
            session_id="missing-main",
        )


def test_unknown_named_entry_is_rejected():
    program = compile_source("main = 42")

    with pytest.raises(ValueError, match="missing"):
        create_initial_core_state(
            program,
            make_config(),
            session_id="unknown-entry",
            entry="missing",
        )


def test_stg_initialization_is_not_supported():
    program = compile_source("main = 42")
    config = make_config()

    from dataclasses import replace

    stg_config = replace(
        config,
        machine_kind=MachineKind.STG,
    )

    with pytest.raises(UnsupportedTransitionError):
        create_initial_core_state(
            program,
            stg_config,
            session_id="stg-not-yet",
        )


def test_global_literal_is_installed_without_evaluation():
    program = compile_source(
        "answer = 42\n"
        "main = answer"
    )

    heap = Heap()
    environment = _reserve_global_scope(
        heap, program.bindings
    )

    reference = environment.lookup("answer")
    original_slots = heap.current_slots

    installed = _install_global_rhs(
        heap, environment, program.bindings[0], Strategy.CBV
    )

    assert installed is reference
    assert heap.current_slots == original_slots
    assert heap.get(reference).value.expression == CoreInt(42)
    assert isinstance(
        heap.get(reference).value, PendingGlobal
    )

    # The other global has not been installed.
    assert isinstance(
        heap.get(environment.lookup("main")).value,
        Reserved,
    )


def test_global_alias_is_not_resolved_during_installation():
    program = compile_source(
        "main = answer\n"
        "answer = 42"
    )

    heap = Heap()
    environment = _reserve_global_scope(
        heap, program.bindings
    )

    main_ref = environment.lookup("main")
    answer_ref = environment.lookup("answer")

    _install_global_rhs(
        heap, environment, program.bindings[0], Strategy.CBV
    )

    pending = heap.get(main_ref).value

    assert isinstance(pending, PendingGlobal)
    assert pending.expression.name == "answer"
    assert isinstance(heap.get(answer_ref).value, Reserved)


@pytest.mark.parametrize("strategy", list(Strategy))
def test_global_lambda_installs_closure_without_running_body(strategy):
    program = compile_source(
        "identity x = x\n"
        "main = identity"
    )

    heap = Heap()
    environment = _reserve_global_scope(
        heap, program.bindings
    )

    reference = environment.lookup("identity")
    slots_before = heap.current_slots

    _install_global_rhs(
        heap, environment, program.bindings[0], strategy
    )

    closure = heap.get(reference).value

    assert isinstance(closure, Closure)
    assert closure.lambda_expression.parameter == "x"
    assert closure.captured_locals.bindings == {}
    assert closure.required_slots == 1
    assert heap.current_slots == slots_before

    # Its body has not been evaluated.
    assert isinstance(
        heap.get(environment.lookup("main")).value,
        Reserved,
    )


@pytest.mark.parametrize("strategy", list(Strategy))
def test_all_global_installations_preserve_addresses(strategy):
    program = compile_source(
        "first = second\n"
        "second = 42\n"
        "main = first"
    )

    heap = Heap()
    environment = _reserve_global_scope(
        heap, program.bindings
    )

    references = {
        binding.name: environment.lookup(binding.name)
        for binding in program.bindings
    }
    initial_slots = heap.current_slots
    next_object_id = heap.next_object_id

    for binding in program.bindings:
        installed = _install_global_rhs(heap, environment, binding, strategy)
        assert installed is references[binding.name]

    for binding in program.bindings:
        reference = references[binding.name]
        assert environment.lookup(binding.name) is reference
        cell = heap.get(reference)
        assert cell.allocated_slots == 1
        if strategy is Strategy.CBNEED:
            assert isinstance(cell.value, PendingThunk)
            payload = heap.get(cell.value.payload_reference).value
            assert isinstance(payload, ThunkPayload)
            assert payload.expression is binding.rhs
            assert not payload.captured_locals.bindings
            assert payload.captured_locals.parent is None
        else:
            assert isinstance(cell.value, PendingGlobal)

    payload_count = len(program.bindings) if strategy is Strategy.CBNEED else 0
    assert heap.current_slots == initial_slots + payload_count
    assert heap.next_object_id == next_object_id + payload_count


@pytest.mark.parametrize("strategy", list(Strategy))
def test_installing_shadowed_seq_keeps_builtin_unchanged(strategy):
    program = compile_source(
        "seq x y = x\n"
        "main = seq 1 2"
    )

    heap = Heap()
    environment = _reserve_global_scope(
        heap, program.bindings
    )

    builtin_ref = environment.parent.lookup("seq")
    user_ref = environment.lookup("seq")

    _install_global_rhs(
        heap, environment, program.bindings[0], strategy
    )

    assert isinstance(heap.get(user_ref).value, Closure)
    assert isinstance(
        heap.get(builtin_ref).value,
        PredefinedFunction,
    )


@pytest.mark.parametrize("strategy", list(Strategy))
def test_reinstalling_global_is_rejected_without_mutation(strategy):
    program = compile_source("main = 42")

    heap = Heap()
    environment = _reserve_global_scope(
        heap, program.bindings
    )

    binding = program.bindings[0]
    reference = environment.lookup("main")

    _install_global_rhs(heap, environment, binding, strategy)
    installed_cell = heap.get(reference)
    cells_before = dict(heap.cells)
    slots_before = heap.current_slots
    next_id_before = heap.next_object_id

    with pytest.raises(ValueError, match="already initialized"):
        _install_global_rhs(heap, environment, binding, strategy)

    assert heap.get(reference) is installed_cell
    assert dict(heap.cells) == cells_before
    assert heap.current_slots == slots_before
    assert heap.next_object_id == next_id_before


@pytest.mark.parametrize("strategy", list(Strategy))
def test_unreserved_global_cannot_be_installed(strategy):
    program = compile_source("main = 42")

    heap = Heap()
    environment = _reserve_global_scope(
        heap, program.bindings
    )

    extra_binding = CoreBinding("missing", CoreInt(1))
    slots_before = heap.current_slots

    with pytest.raises(UnboundNameError):
        _install_global_rhs(
            heap, environment, extra_binding, strategy
        )

    assert heap.current_slots == slots_before


def test_pending_global_rejects_non_core_expression():
    with pytest.raises(TypeError):
        PendingGlobal("42")


@pytest.mark.parametrize("strategy", list(Strategy))
def test_initialization_reserves_scope_in_one_transition(strategy):
    program = compile_source(
        "first = second\n"
        "second = 42\n"
        "main = first"
    )
    config = make_config(strategy)
    original = create_initial_core_state(
        program,
        config,
        session_id="reserve-test",
    )

    transition = step(original, config)
    next_state = transition.next_state
    machine = next_state.machine_state

    assert transition.rule_id == "CORE_INIT_RESERVE_GLOBAL_SCOPE"
    assert transition.phase_before is ExecutionPhase.INITIALIZATION
    assert transition.phase_after is ExecutionPhase.INITIALIZATION

    assert isinstance(machine.control, InitializeCoreBindings)
    assert machine.control.scope_reserved is True
    assert machine.control.next_index == 0

    assert set(machine.global_environment.bindings) == {
        "first", "second", "main"
    }

    assert all(
        isinstance(
            machine.heap.get(
                machine.global_environment.lookup(name)
            ).value,
            Reserved,
        )
        for name in ("first", "second", "main")
    )

    assert original.machine_state.heap.current_slots == 0
    assert original.machine_state.global_environment.bindings == {}
    assert next_state.transition_index == 1
    assert machine.evaluator_transition_count == 1


@pytest.mark.parametrize("strategy", list(Strategy))
def test_each_installation_advances_one_binding(strategy):
    program = compile_source(
        "answer = 42\n"
        "identity x = x\n"
        "main = answer"
    )
    config = make_config(strategy)
    initial = create_initial_core_state(
        program,
        config,
        session_id="install-test",
    )

    reserved = step(initial, config).next_state
    reserved_machine = reserved.machine_state
    answer_ref = reserved_machine.global_environment.lookup("answer")
    first = step(reserved, config)
    first_machine = first.next_state.machine_state

    assert first.rule_id == "CORE_INIT_INSTALL_GLOBAL"
    assert first_machine.control.next_index == 1

    environment = first_machine.global_environment
    assert environment.lookup("answer") is answer_ref
    assert isinstance(reserved_machine.heap.get(answer_ref).value, Reserved)
    assert first_machine.heap.get(answer_ref).allocated_slots == 1

    assert isinstance(
        first_machine.heap.get(
            environment.lookup("answer")
        ).value,
        PendingThunk if strategy is Strategy.CBNEED else PendingGlobal,
    )
    assert isinstance(
        first_machine.heap.get(
            environment.lookup("identity")
        ).value,
        Reserved,
    )
    assert first_machine.stack.depth == 0

    second = step(first.next_state, config)
    second_machine = second.next_state.machine_state

    assert second.rule_id == "CORE_INIT_INSTALL_GLOBAL"
    assert second_machine.control.next_index == 2

    assert isinstance(
        second_machine.heap.get(
            second_machine.global_environment.lookup("identity")
        ).value,
        Closure,
    )

    # Installing the second RHS cannot alter the first snapshot.
    assert isinstance(
        first_machine.heap.get(
            environment.lookup("identity")
        ).value,
        Reserved,
    )


@pytest.mark.parametrize("strategy", list(Strategy))
def test_initialization_enters_selected_global(strategy):
    program = compile_source(
        "loop = loop\n"
        "main = 42"
    )
    config = make_config(strategy)
    initial = create_initial_core_state(
        program,
        config,
        session_id="entry-test",
    )

    current = initial
    transitions = []

    for _ in range(len(program.bindings) + 2):
        transition = step(current, config)
        transitions.append(transition)
        current = transition.next_state

    machine = current.machine_state

    assert machine.phase is ExecutionPhase.EVALUATION
    assert machine.control == EvaluateCore(CoreVar("main"))
    assert machine.strategy is strategy

    assert [
        item.rule_id for item in transitions
    ] == [
        "CORE_INIT_RESERVE_GLOBAL_SCOPE",
        "CORE_INIT_INSTALL_GLOBAL",
        "CORE_INIT_INSTALL_GLOBAL",
        "CORE_INIT_ENTER_ENTRY",
    ]

    assert isinstance(
        machine.heap.get(
            machine.global_environment.lookup("loop")
        ).value,
        PendingThunk if strategy is Strategy.CBNEED else PendingGlobal,
    )

    assert current.transition_index == 4
    assert machine.evaluator_transition_count == 4
    assert initial.machine_state.heap.current_slots == 0


def test_batch_can_stop_at_initialization_boundary():
    program = compile_source("main = 42")
    config = make_config()
    initial = create_initial_core_state(
        program,
        config,
        session_id="batch-initialization",
    )

    result = run_batch(
        initial,
        config,
        max_steps=len(program.bindings) + 2,
    )

    assert result.stop_reason is BatchStopReason.BATCH_LIMIT
    assert [
        entry.rule_id for entry in result.trace
    ] == [
        "CORE_INIT_RESERVE_GLOBAL_SCOPE",
        "CORE_INIT_INSTALL_GLOBAL",
        "CORE_INIT_ENTER_ENTRY",
    ]

    assert result.state.machine_state.control == EvaluateCore(
        CoreVar("main")
    )
    assert result.state.machine_state.phase is ExecutionPhase.EVALUATION


def test_explicit_expression_runs_after_empty_global_group():
    program = compile_source("")
    config = make_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="empty-program",
        entry=CoreInt(9),
    )

    result = run_batch(
        initial,
        config,
        max_steps=10,
    )

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert result.state.machine_state.control == Return(
        ImmediateInteger(9)
    )

    assert [
        entry.rule_id for entry in result.trace
    ] == [
        "CORE_INIT_RESERVE_GLOBAL_SCOPE",
        "CORE_INIT_ENTER_ENTRY",
        "CORE_EVAL_INTEGER",
    ]


def test_initialization_respects_evaluator_budget():
    program = compile_source("main = 42")
    config = replace(
        make_config(),
        execution_step_limit=1,
    )

    initial = create_initial_core_state(
        program,
        config,
        session_id="budget-test",
    )

    after_reservation = step(initial, config).next_state

    with pytest.raises(EvaluatorBudgetExhaustedError):
        step(after_reservation, config)

    assert after_reservation.transition_index == 1
    assert after_reservation.machine_state.control.next_index == 0
    assert after_reservation.machine_state.evaluator_transition_count == 1

def test_compiled_letrec_enters_reserved_local_scope():
    program = compile_source(
        "main = let { x = 10; y = x } in y"
    )
    config = make_config(strategy=Strategy.CBV)

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbv-local-scope",
    )

    current = initial

    for _ in range(30):
        control = current.machine_state.control

        if (
            isinstance(control, EvaluateCore)
            and isinstance(control.expression, CoreLetRec)
        ):
            break

        current = step(current, config).next_state
    else:
        pytest.fail("Compiled CoreLetRec was never reached")

    previous = current
    transition = step(previous, config)
    machine = transition.next_state.machine_state

    assert transition.rule_id is RuleId.CORE_LETREC_RESERVE_SCOPE
    assert isinstance(machine.control, InitializeLocalBindings)

    assert set(machine.local_environment.bindings) == {"x", "y"}
    assert machine.local_environment.parent is (
        previous.machine_state.local_environment
    )

    assert machine.stack.depth == (
        previous.machine_state.stack.depth + 1
    )

    assert isinstance(
        machine.stack.peek(),
        RestoreEnvironmentFrame,
    )

    assert previous.machine_state.stack.depth + 1 == machine.stack.depth
    assert previous.machine_state.heap.current_slots + 2 == (
        machine.heap.current_slots
    )

    assert initial.transition_index == 0
    assert initial.machine_state.heap.current_slots == 0

    
def test_local_recursive_functions_use_stable_indirections():
    program = compile_source(
        "main = let { f x = g x; g y = f y } in f"
    )
    config = make_config(strategy=Strategy.CBV)

    state = create_initial_core_state(
        program,
        config,
        session_id="recursive-functions",
    )

    for _ in range(30):
        if isinstance(
            state.machine_state.control,
            InitializeLocalBindings,
        ):
            break
        state = step(state, config).next_state
    else:
        pytest.fail("Local initialization was not reached")

    reserved = state.machine_state
    f_ref = reserved.local_environment.lookup("f")
    g_ref = reserved.local_environment.lookup("g")

    assert isinstance(reserved.heap.get(f_ref).value, Reserved)
    assert isinstance(reserved.heap.get(g_ref).value, Reserved)

    first = step(state, config)
    first_machine = first.next_state.machine_state

    assert first.rule_id is RuleId.CORE_LETREC_INSTALL_FUNCTION
    assert first_machine.control.next_index == 1

    f_indirection = first_machine.heap.get(f_ref).value
    assert isinstance(f_indirection, Indirection)

    f_closure = first_machine.heap.get(
        f_indirection.target
    ).value

    assert isinstance(f_closure, Closure)
    assert f_closure.captured_locals.lookup("g") == g_ref

    # g still has its original reserved cell.
    assert isinstance(first_machine.heap.get(g_ref).value, Reserved)

    second = step(first.next_state, config)
    machine = second.next_state.machine_state

    assert second.rule_id is RuleId.CORE_LETREC_INSTALL_FUNCTION
    assert machine.control.next_index == 2

    g_indirection = machine.heap.get(g_ref).value
    assert isinstance(g_indirection, Indirection)

    g_closure = machine.heap.get(
        g_indirection.target
    ).value

    assert isinstance(g_closure, Closure)
    assert g_closure.captured_locals.lookup("f") == f_ref

    # Stable anchors and exact closure capacities.
    assert machine.heap.get(f_ref).allocated_slots == 1
    assert machine.heap.get(g_ref).allocated_slots == 1
    assert machine.heap.get(f_indirection.target).allocated_slots == 2
    assert machine.heap.get(g_indirection.target).allocated_slots == 2

    # Previous snapshots remain unchanged.
    assert isinstance(reserved.heap.get(f_ref).value, Reserved)
    assert isinstance(reserved.heap.get(g_ref).value, Reserved)
    assert isinstance(first_machine.heap.get(g_ref).value, Reserved)


def test_local_value_rhs_is_initialized_strictly():
    program = compile_source(
        "main = let { x = 10; y = x + 2 } in y"
    )
    config = make_config(strategy=Strategy.CBV)

    state = create_initial_core_state(
        program,
        config,
        session_id="local-strict-init",
    )

    for _ in range(30):
        if isinstance(
            state.machine_state.control,
            InitializeLocalBindings,
        ):
            break
        state = step(state, config).next_state
    else:
        pytest.fail("Local initialization was not reached")

    reserved_state = state
    reserved_machine = state.machine_state

    x_ref = reserved_machine.local_environment.lookup("x")
    y_ref = reserved_machine.local_environment.lookup("y")

    assert isinstance(reserved_machine.heap.get(x_ref).value, Reserved)
    assert isinstance(reserved_machine.heap.get(y_ref).value, Reserved)

    # Start evaluating x = 10.
    transition = step(state, config)
    state = transition.next_state

    assert transition.rule_id is RuleId.CORE_LETREC_EVAL_VALUE
    assert state.machine_state.control == EvaluateCore(CoreInt(10))
    assert isinstance(
        state.machine_state.stack.peek(),
        LocalValueInitializationFrame,
    )

    # Evaluate, demand and store the first RHS.
    result = run_batch(state, config, max_steps=4)
    machine = result.state.machine_state

    assert [entry.rule_id for entry in result.trace] == [
        RuleId.CORE_EVAL_INTEGER,
        RuleId.CORE_LETREC_REQUIRE_VALUE_WHNF,
        RuleId.CORE_FORCE_IMMEDIATE,
        RuleId.CORE_LETREC_STORE_VALUE,
    ]

    assert isinstance(machine.control, InitializeLocalBindings)
    assert machine.control.next_index == 1

    x_cell = machine.heap.get(x_ref)
    y_cell = machine.heap.get(y_ref)

    assert x_cell.value == Indirection(ImmediateInteger(10))
    assert isinstance(y_cell.value, Reserved)

    # Previous snapshots must remain unchanged.
    assert isinstance(
        reserved_state.machine_state.heap.get(x_ref).value,
        Reserved,
    )
    assert isinstance(
        reserved_state.machine_state.heap.get(y_ref).value,
        Reserved,
    )


def test_strict_local_forward_value_dependency_fails():
    program = compile_source(
        "main = let { x = y; y = 10 } in x"
    )
    config = make_config(strategy=Strategy.CBV)

    initial = create_initial_core_state(
        program,
        config,
        session_id="forward-value-dependency",
    )

    with pytest.raises(
        InvalidMachineStateError,
        match="uninitialized",
    ):
        run_batch(initial, config, max_steps=100)

    assert initial.transition_index == 0
    assert initial.machine_state.heap.current_slots == 0


@pytest.mark.parametrize(
    "source,uninitialized_name",
    [
        (
            "main = let { x = y; y = 10 } in x",
            "y",
        ),
        (
            "main = let { x = x } in x",
            "x",
        ),
        (
            "main = let { x = y; y = x } in x",
            "y",
        ),
        (
            "main = let { x = f 1; f y = y } in x",
            "f",
        ),
    ],
)
def test_cbv_rejects_premature_local_binding_demand(
    source,
    uninitialized_name,
):
    program = compile_source(source)
    config = make_config(strategy=Strategy.CBV)

    initial = create_initial_core_state(
        program,
        config,
        session_id="local-initialization-error",
    )

    with pytest.raises(
        UninitializedLocalBindingError,
        match=rf"Local binding '{uninitialized_name}' is uninitialized",
    ):
        run_batch(initial, config, max_steps=100)

    assert initial.transition_index == 0
    assert initial.machine_state.heap.current_slots == 0
    assert initial.machine_state.stack.depth == 0


def test_failed_local_initialization_preserves_previous_snapshot():
    program = compile_source(
        "main = let { x = y; y = 10 } in x"
    )
    config = make_config(strategy=Strategy.CBV)

    current = create_initial_core_state(
        program,
        config,
        session_id="local-init-snapshot",
    )

    for _ in range(100):
        control = current.machine_state.control

        if (
            isinstance(control, Force)
            and isinstance(control.reference, HeapReference)
            and isinstance(
                current.machine_state.heap.get(
                    control.reference
                ).value,
                Reserved,
            )
        ):
            break

        current = step(current, config).next_state
    else:
        pytest.fail("Uninitialized local demand was never reached")

    machine = current.machine_state

    state_id = current.state_id
    transition_index = current.transition_index
    stack_frames = machine.stack.frames
    heap_cells = dict(machine.heap.cells)

    assert any(
        isinstance(frame, LocalValueInitializationFrame)
        for frame in stack_frames
    )

    with pytest.raises(UninitializedLocalBindingError):
        step(current, config)

    assert current.state_id == state_id
    assert current.transition_index == transition_index
    assert machine.stack.frames == stack_frames
    assert dict(machine.heap.cells) == heap_cells
    assert isinstance(
        machine.heap.get(control.reference).value,
        Reserved,
    )


@pytest.mark.parametrize(
    "source,expected",
    [
        (
            "main = let { f x = g x; g y = y } in f 5",
            5,
        ),
        (
            "main = let { f x = f x } in 10",
            10,
        ),
        (
            "main = let { f x = x + 1; y = f 4 } in y",
            5,
        ),
    ],
)
def test_cbv_function_recursion_does_not_require_eager_bodies(
    source,
    expected,
):
    program = compile_source(source)
    config = make_config(strategy=Strategy.CBV)

    initial = create_initial_core_state(
        program,
        config,
        session_id="local-function-recursion",
    )

    result = run_batch(initial, config, max_steps=200)
    machine = result.state.machine_state

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert machine.control == Return(
        ImmediateInteger(expected)
    )
    assert machine.stack.depth == 0
    assert machine.local_environment is machine.global_environment


def test_nested_letrec_restores_outer_lexical_scope():
    program = compile_source(
        "main = let { x = 10 } in "
        "(let { x = 20; y = x + 1 } in y) + x"
    )
    config = make_config(strategy=Strategy.CBV)

    initial = create_initial_core_state(
        program,
        config,
        session_id="nested-local-environments",
    )

    result = run_batch(initial, config, max_steps=200)
    machine = result.state.machine_state

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert machine.control == Return(ImmediateInteger(31))
    assert machine.stack.depth == 0
    assert machine.local_environment is machine.global_environment

    rules = [entry.rule_id for entry in result.trace]

    assert rules.count(RuleId.CORE_LETREC_RESERVE_SCOPE) == 2
    assert rules.count(RuleId.CORE_RESTORE_CALLER_ENVIRONMENT) >= 2


def test_cbv_letrec_preserves_anchor_identity_and_slot_accounting():
    program = compile_source(
        "main = let { f z = x + z; x = 40; y = f 2 } in y"
    )
    config = make_config(strategy=Strategy.CBV)

    current = create_initial_core_state(
        program,
        config,
        session_id="letrec-allocation-audit",
    )

    for _ in range(50):
        transition = step(current, config)

        if transition.rule_id is RuleId.CORE_LETREC_RESERVE_SCOPE:
            before_reservation = current
            reserved = transition.next_state
            break

        current = transition.next_state
    else:
        pytest.fail("Local scope reservation was not reached")

    reserved_machine = reserved.machine_state
    environment = reserved_machine.local_environment

    f_ref = environment.lookup("f")
    x_ref = environment.lookup("x")
    y_ref = environment.lookup("y")

    assert len({f_ref, x_ref, y_ref}) == 3

    for reference in (f_ref, x_ref, y_ref):
        assert isinstance(
            reserved_machine.heap.get(reference).value,
            Reserved,
        )

    # Exactly one administrative slot per binding.
    assert (
        reserved_machine.heap.current_slots
        - before_reservation.machine_state.heap.current_slots
    ) == 3

    result = run_batch(reserved, config, max_steps=100)
    machine = result.state.machine_state

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    assert machine.control == Return(ImmediateInteger(42))

    # The binding addresses are unchanged.
    f_cell = machine.heap.get(f_ref)
    x_cell = machine.heap.get(x_ref)
    y_cell = machine.heap.get(y_ref)

    assert f_cell.allocated_slots == 1
    assert x_cell.allocated_slots == 1
    assert y_cell.allocated_slots == 1

    assert isinstance(f_cell.value, Indirection)
    assert x_cell.value == Indirection(ImmediateInteger(40))
    assert y_cell.value == Indirection(ImmediateInteger(42))

    closure_ref = f_cell.value.target
    closure_cell = machine.heap.get(closure_ref)

    assert isinstance(closure_cell.value, Closure)
    assert closure_cell.value.captured_locals.lookup("x") == x_ref
    assert closure_cell.allocated_slots == 2

    # Only the captured closure needed an additional
    # allocation after reserving the binding cells.
    assert (
        machine.heap.current_slots
        - reserved_machine.heap.current_slots
    ) == 2

    assert (
        machine.heap.next_object_id
        - reserved_machine.heap.next_object_id
    ) == 1

    # Snapshot isolation.
    for reference in (f_ref, x_ref, y_ref):
        assert isinstance(
            reserved_machine.heap.get(reference).value,
            Reserved,
        )

    assert machine.stack.depth == 0
    assert machine.local_environment is machine.global_environment


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
def test_heap_baseline_recorded_once_after_global_initialization(
    strategy,
):
    program = compile_source(
        "answer = 42\n"
        "main = answer"
    )

    config = make_config(strategy)

    state = create_initial_core_state(
        program,
        config,
        session_id="heap-baseline-test",
    )

    metrics = InstrumentationState()
    baseline_effects = []

    # Reservation + one installation per binding + entry.
    initialization_steps = len(program.bindings) + 2

    for index in range(initialization_steps):
        transition = step(state, config)

        effects = [
            effect
            for effect in transition.heap_effects
            if isinstance(effect, HeapBaselineRecorded)
        ]

        if index < initialization_steps - 1:
            assert effects == []
        else:
            assert transition.rule_id is RuleId.CORE_INIT_ENTER_ENTRY
            assert len(effects) == 1

        baseline_effects.extend(effects)

        metrics = reduce_metrics(metrics, transition)
        state = transition.next_state

    assert len(baseline_effects) == 1

    baseline = baseline_effects[0]

    assert baseline.slots == state.machine_state.heap.current_slots
    assert metrics.baseline_slots == baseline.slots
    assert metrics.counters.current_heap_slots == baseline.slots
    assert metrics.counters.peak_heap_slots == baseline.slots
    assert metrics.additional_peak_over_baseline == 0

    assert state.machine_state.phase is ExecutionPhase.EVALUATION


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
def test_heap_metrics_match_actual_heap_during_execution(strategy):
    program = compile_source(
        "main = let { x = 1 } in x"
    )

    config = make_config(strategy)

    initial = create_initial_core_state(
        program,
        config,
        session_id="heap-metrics-integration",
    )

    current = initial
    metrics = InstrumentationState()

    observed_peak = 0
    allocated_ids = set()
    baselines = []

    for _ in range(100):
        transition = step(current, config)

        next_state = transition.next_state
        heap = next_state.machine_state.heap

        for effect in transition.heap_effects:
            if isinstance(effect, HeapAllocated):
                assert effect.object_id not in allocated_ids
                allocated_ids.add(effect.object_id)

            elif isinstance(effect, HeapBaselineRecorded):
                baselines.append(effect)

                assert (
                    transition.phase_after
                    is ExecutionPhase.EVALUATION
                )

        metrics = reduce_metrics(metrics, transition)

        # Independently inspect actual allocated capacity.
        actual_slots = sum(
            cell.allocated_slots
            for cell in heap.cells.values()
        )

        observed_peak = max(observed_peak, actual_slots)

        counters = metrics.counters

        assert counters.current_heap_slots == actual_slots
        assert counters.peak_heap_slots == observed_peak

        assert counters.total_allocations == len(
            allocated_ids
        )

        assert counters.total_allocations == len(heap.cells)

        current = next_state

        if (
            core_machine._stop_reason(current, config)
            is BatchStopReason.WHNF_PENDING
        ):
            break
    else:
        pytest.fail("Execution did not reach WHNF")

    assert len(baselines) == 1
    assert metrics.baseline_slots == baselines[0].slots

    # The local let allocates after global initialization.
    assert (
        metrics.counters.peak_heap_slots
        > metrics.baseline_slots
    )

    assert metrics.additional_peak_over_baseline == (
        metrics.counters.peak_heap_slots
        - metrics.baseline_slots
    )

    # Historical execution state remains untouched.
    assert initial.machine_state.heap.current_slots == 0
    assert initial.transition_index == 0


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
def test_global_thunk_creation_emits_stable_anchor_event(strategy):
    program = compile_source(
        "answer = 42\n"
        "main = answer"
    )
    config = make_config(strategy)

    initial = create_initial_core_state(
        program,
        config,
        session_id="global-thunk-creation",
    )

    reserved = step(initial, config)
    installed = step(reserved.next_state, config)

    anchor = (
        installed.next_state.machine_state
        .global_environment.lookup("answer")
    )

    creation_events = [
        event
        for event in installed.semantic_events
        if event.kind is SemanticEventKind.THUNK_CREATED
    ]

    if strategy is Strategy.CBNEED:
        assert len(creation_events) == 1
        assert creation_events[0].object_id == anchor.object_id
    else:
        assert creation_events == []
