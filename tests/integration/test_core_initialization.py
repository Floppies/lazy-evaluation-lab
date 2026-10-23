import pytest

from dataclasses import replace

from lazy_lab.core.nodes import CoreBinding, CoreInt
from lazy_lab.engine.core_machine import (
    _reserve_global_scope,
    _install_global_rhs,
    step,
    run_batch,
    BatchStopReason,
    EvaluatorBudgetExhaustedError
)
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.environment import (
    UnboundNameError,
)
from lazy_lab.runtime.heap import Heap, Reserved
from lazy_lab.runtime.predefined import PredefinedFunction
from lazy_lab.runtime.references import HeapReference, ImmediateInteger
from lazy_lab.core.nodes import CoreInt, CoreVar
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
)
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.control import (
    InitializeCoreBindings,
    EvaluateCore,
    Return
)
from lazy_lab.runtime.global_bindings import PendingGlobal
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
        heap, environment, program.bindings[0]
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
        heap, environment, program.bindings[0]
    )

    pending = heap.get(main_ref).value

    assert isinstance(pending, PendingGlobal)
    assert pending.expression.name == "answer"
    assert isinstance(heap.get(answer_ref).value, Reserved)


def test_global_lambda_installs_closure_without_running_body():
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
        heap, environment, program.bindings[0]
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


def test_all_global_installations_preserve_addresses():
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
        _install_global_rhs(heap, environment, binding)

    for name, reference in references.items():
        assert environment.lookup(name) is reference
        assert isinstance(
            heap.get(reference).value, PendingGlobal
        )

    assert heap.current_slots == initial_slots
    assert heap.next_object_id == next_object_id


def test_installing_shadowed_seq_keeps_builtin_unchanged():
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
        heap, environment, program.bindings[0]
    )

    assert isinstance(heap.get(user_ref).value, Closure)
    assert isinstance(
        heap.get(builtin_ref).value,
        PredefinedFunction,
    )


def test_reinstalling_global_is_rejected_without_mutation():
    program = compile_source("main = 42")

    heap = Heap()
    environment = _reserve_global_scope(
        heap, program.bindings
    )

    binding = program.bindings[0]
    reference = environment.lookup("main")

    _install_global_rhs(heap, environment, binding)
    installed_cell = heap.get(reference)

    with pytest.raises(ValueError, match="already initialized"):
        _install_global_rhs(heap, environment, binding)

    assert heap.get(reference) is installed_cell


def test_unreserved_global_cannot_be_installed():
    program = compile_source("main = 42")

    heap = Heap()
    environment = _reserve_global_scope(
        heap, program.bindings
    )

    extra_binding = CoreBinding("missing", CoreInt(1))
    slots_before = heap.current_slots

    with pytest.raises(UnboundNameError):
        _install_global_rhs(
            heap, environment, extra_binding
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


def test_each_installation_advances_one_binding():
    program = compile_source(
        "answer = 42\n"
        "identity x = x\n"
        "main = answer"
    )
    config = make_config()
    initial = create_initial_core_state(
        program,
        config,
        session_id="install-test",
    )

    reserved = step(initial, config).next_state
    first = step(reserved, config)
    first_machine = first.next_state.machine_state

    assert first.rule_id == "CORE_INIT_INSTALL_GLOBAL"
    assert first_machine.control.next_index == 1

    environment = first_machine.global_environment

    assert isinstance(
        first_machine.heap.get(
            environment.lookup("answer")
        ).value,
        PendingGlobal,
    )
    assert isinstance(
        first_machine.heap.get(
            environment.lookup("identity")
        ).value,
        Reserved,
    )

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
        PendingGlobal,
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
