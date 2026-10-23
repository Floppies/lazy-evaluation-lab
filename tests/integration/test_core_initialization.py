import pytest

from lazy_lab.core.nodes import CoreBinding, CoreInt
from lazy_lab.engine.core_machine import _reserve_global_scope
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.environment import (
    UnboundNameError,
)
from lazy_lab.runtime.heap import Heap, Reserved
from lazy_lab.runtime.predefined import PredefinedFunction
from lazy_lab.runtime.references import HeapReference
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
from lazy_lab.runtime.control import InitializeCoreBindings

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