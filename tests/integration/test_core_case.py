import pytest

from lazy_lab.core.nodes import (
    CoreCase,
    CoreCon,
    CoreConAlt,
    CoreDefaultAlt,
    CoreInt,
    CoreVar,
)
from lazy_lab.pipeline import compile_source
from lazy_lab.engine.core_machine import (
    create_initial_core_state,
    step,
)
from lazy_lab.runtime.constructors import ConstructorValue
from lazy_lab.runtime.control import EvaluateCore, Force, Return
from lazy_lab.runtime.stack import CoreCaseFrame
from lazy_lab.runtime.state import Strategy
from lazy_lab.runtime.transitions import RuleId

from tests.integration.test_core_runtime import make_config


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
def test_core_case_starts_with_scrutinee(strategy):
    scrutinee = CoreCon("Nil", ())

    case = CoreCase(
        scrutinee=scrutinee,
        alternatives=(
            CoreConAlt("Nil", (), CoreInt(42)),
        ),
    )

    config = make_config(strategy=strategy)

    current = create_initial_core_state(
        compile_source(""),
        config,
        session_id="case-scrutinee-entry",
        entry=case,
    )

    for _ in range(20):
        transition = step(current, config)
        current = transition.next_state

        if transition.rule_id is RuleId.CORE_EVAL_CASE_SCRUTINEE:
            break
    else:
        raise AssertionError(
            "CoreCase evaluation did not start"
        )

    machine = current.machine_state

    assert isinstance(machine.control, EvaluateCore)
    assert machine.control.expression is scrutinee

    frame = machine.stack.peek()

    assert isinstance(frame, CoreCaseFrame)
    assert frame.alternatives == case.alternatives
    assert frame.awaiting_whnf is False
    assert frame.scrutinee_reference is None


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
def test_case_demands_whnf_and_preserves_original_reference(strategy):
    config = make_config(strategy=strategy)

    case = CoreCase(
        scrutinee=CoreVar("xs"),
        alternatives=(
            CoreConAlt("Nil", (), CoreInt(42)),
        ),
    )

    current = create_initial_core_state(
        compile_source("xs = []"),
        config,
        session_id="case-whnf-demand",
        entry=case,
    )

    saw_demand = False

    for _ in range(100):
        machine = current.machine_state

        if machine.stack.depth:
            frame = machine.stack.peek()

            # Stop immediately after Force has returned WHNF,
            # before alternative selection (B06.5.3).
            if (
                isinstance(frame, CoreCaseFrame)
                and frame.awaiting_whnf
                and isinstance(machine.control, Return)
            ):
                break

        transition = step(current, config)

        if (
            transition.rule_id
            is RuleId.CORE_CASE_REQUIRE_SCRUTINEE_WHNF
        ):
            saw_demand = True

            demanded_machine = transition.next_state.machine_state
            assert isinstance(demanded_machine.control, Force)

        current = transition.next_state

    else:
        raise AssertionError("CoreCase scrutinee did not reach WHNF")

    assert saw_demand

    machine = current.machine_state
    frame = machine.stack.peek()

    original_ref = machine.global_environment.lookup("xs")

    assert frame.scrutinee_reference == original_ref
    assert frame.awaiting_whnf is True

    # Force resolved the original binding into a constructor.
    whnf_ref = machine.control.reference
    assert whnf_ref != original_ref

    value = machine.heap.get(whnf_ref).value
    assert isinstance(value, ConstructorValue)
    assert value.tag == "Nil"


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
def test_case_selects_matching_constructor(strategy):
    config = make_config(strategy=strategy)

    case = CoreCase(
        scrutinee=CoreCon("Nil", ()),
        alternatives=(
            CoreConAlt("Cons", ("h", "t"), CoreInt(1)),
            CoreConAlt("Nil", (), CoreInt(2)),
        ),
    )

    current = create_initial_core_state(
        compile_source(""),
        config,
        session_id="case-constructor-selection",
        entry=case,
    )

    for _ in range(100):
        transition = step(current, config)
        current = transition.next_state

        if (
            transition.rule_id
            is RuleId.CORE_CASE_SELECT_CONSTRUCTOR
        ):
            break
    else:
        raise AssertionError("Constructor alternative was not selected")

    frame = current.machine_state.stack.peek()

    assert isinstance(frame, CoreCaseFrame)
    assert frame.selected_alternative is case.alternatives[1]
    assert frame.selected_alternative.constructor == "Nil"


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
def test_case_default_precedes_constructor(strategy):
    config = make_config(strategy=strategy)

    case = CoreCase(
        scrutinee=CoreCon("Nil", ()),
        alternatives=(
            CoreDefaultAlt("value", CoreInt(10)),
            CoreConAlt("Nil", (), CoreInt(20)),
        ),
    )

    current = create_initial_core_state(
        compile_source(""),
        config,
        session_id="case-default-order",
        entry=case,
    )

    for _ in range(100):
        transition = step(current, config)
        current = transition.next_state

        if (
            transition.rule_id
            is RuleId.CORE_CASE_SELECT_DEFAULT
        ):
            break
    else:
        raise AssertionError("Default alternative was not selected")

    frame = current.machine_state.stack.peek()

    assert isinstance(frame, CoreCaseFrame)
    assert frame.selected_alternative is case.alternatives[0]