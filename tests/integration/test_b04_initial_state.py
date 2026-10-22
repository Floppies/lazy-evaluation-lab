"""Core program initialization entry-point contracts."""

import pytest

from lazy_lab.core.nodes import CoreInt, CoreVar
from lazy_lab.engine.core_machine import (
    UnsupportedTransitionError,
    create_initial_core_state,
)
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.control import InitializeCoreBindings
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionPhase,
    ExecutionStatus,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)


def make_config(strategy=Strategy.CBNEED):
    return ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=strategy,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=100,
        result_node_limit=100,
        trace_mode=TraceMode.FULL,
    )


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
