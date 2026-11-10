from dataclasses import replace

import pytest

from lazy_lab.core.nodes import (
    CoreCase,
    CoreCon,
    CoreConAlt,
    CoreDefaultAlt,
    CoreInt,
    CorePrimOp,
    CoreVar,
)
from lazy_lab.pipeline import compile_source
from lazy_lab.engine.core_machine import (
    PatternMatchError,
    create_initial_core_state,
    run_batch,
    step,
)
from lazy_lab.runtime.constructors import ConstructorValue
from lazy_lab.runtime.control import EvaluateCore, Force, Return
from lazy_lab.runtime.references import ImmediateInteger
from lazy_lab.runtime.stack import CoreCaseFrame, RestoreEnvironmentFrame
from lazy_lab.runtime.state import Strategy
from lazy_lab.runtime.thunks import PendingThunk
from lazy_lab.runtime.transitions import BatchStopReason, RuleId

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


def test_cons_binders_preserve_reference():
    config = make_config(strategy=Strategy.CBNEED)

    case = CoreCase(
        scrutinee=CoreCon("Cons", (CoreVar("loop"), CoreVar("loop"))),
        alternatives=(
            CoreConAlt("Cons", ("h", "t"), CoreInt(99)),
        ),
    )

    current = create_initial_core_state(
        compile_source("loop = loop"),
        config,
        session_id="case-cons-binders",
        entry=case,
    )

    for _ in range(100):
        control = current.machine_state.control
        transition = step(current, config)
        current = transition.next_state

        if (
            transition.rule_id
            is RuleId.CORE_CASE_ENTER_CONSTRUCTOR_BODY
        ):
            break
    else:
        raise AssertionError("Constructor alternative body was not entered")

    machine = current.machine_state

    assert isinstance(control, Return)
    constructor = machine.heap.get(control.reference).value
    assert isinstance(constructor, ConstructorValue)
    assert constructor.tag == "Cons"
    assert len(constructor.fields) == 2

    assert machine.local_environment.lookup("h") is constructor.fields[0]
    assert machine.local_environment.lookup("t") is constructor.fields[1]

    for field_ref in constructor.fields:
        assert isinstance(machine.heap.get(field_ref).value, PendingThunk)

    assert machine.control == EvaluateCore(CoreInt(99))
    assert isinstance(machine.stack.peek(), RestoreEnvironmentFrame)

    result = run_batch(current, config, max_steps=100)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    final_machine = result.state.machine_state
    assert final_machine.control == Return(ImmediateInteger(99))

    for field_ref in constructor.fields:
        assert isinstance(final_machine.heap.get(field_ref).value, PendingThunk)


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
def test_default_preserve_original_refence(strategy):
    config = make_config(strategy=strategy)

    case = CoreCase(
        scrutinee=CoreVar("xs"),
        alternatives=(
            CoreDefaultAlt("whole", CoreVar("whole")),
        ),
    )

    current = create_initial_core_state(
        compile_source("xs = []"),
        config,
        session_id="case-default-original-reference",
        entry=case,
    )
    original_environment = None

    for _ in range(100):
        before = current.machine_state
        transition = step(current, config)
        current = transition.next_state

        if transition.rule_id is RuleId.CORE_EVAL_CASE_SCRUTINEE:
            original_environment = before.local_environment

        if transition.rule_id is RuleId.CORE_CASE_ENTER_DEFAULT_BODY:
            break
    else:
        raise AssertionError("Default alternative body was not entered")

    machine = current.machine_state

    assert (
        machine.local_environment.lookup("whole")
        == machine.global_environment.lookup("xs")
    )
    assert machine.control == EvaluateCore(CoreVar("whole"))

    frame = machine.stack.peek()
    assert isinstance(frame, RestoreEnvironmentFrame)
    assert original_environment is not None
    assert frame.environment is original_environment
    assert machine.local_environment.parent is original_environment

    result = run_batch(current, config, max_steps=100)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING
    final_machine = result.state.machine_state
    assert final_machine.local_environment is original_environment
    assert final_machine.stack.depth == 0


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
@pytest.mark.parametrize(
    "argument, expected",
    [
        ("[]", 0),
        ("((1 + 2) : [])", 3),
        ("True", 99),
    ],
)
def test_surface_pattern_matching_end_to_end(
    strategy,
    argument,
    expected,
):
    source = (
        "choose [] = 0\n"
        "choose (h:t) = h\n"
        "choose other = 99\n"
        f"main = choose {argument}"
    )

    config = replace(
        make_config(strategy=strategy),
        execution_step_limit=300,
    )

    initial = create_initial_core_state(
        compile_source(source),
        config,
        session_id="case-end-to-end",
    )

    result = run_batch(initial, config, max_steps=300)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    machine = result.state.machine_state

    assert machine.control == Return(
        ImmediateInteger(expected)
    )
    assert machine.stack.depth == 0


def test_case_constructor_demand_differs_between_strategies():
    source = (
        "loop = loop\n"
        "isCons [] = 0\n"
        "isCons (h:t) = 1\n"
        "main = isCons (42 : loop)"
    )

    program = compile_source(source)

    need_config = replace(
        make_config(strategy=Strategy.CBNEED),
        execution_step_limit=100,
    )

    need_initial = create_initial_core_state(
        program,
        need_config,
        session_id="case-lazy-demand",
    )

    need_result = run_batch(
        need_initial,
        need_config,
        max_steps=100,
    )

    assert need_result.stop_reason is BatchStopReason.WHNF_PENDING
    assert need_result.state.machine_state.control == Return(
        ImmediateInteger(1)
    )

    cbv_config = replace(
        make_config(strategy=Strategy.CBV),
        execution_step_limit=100,
    )

    cbv_initial = create_initial_core_state(
        program,
        cbv_config,
        session_id="case-strict-demand",
    )

    cbv_result = run_batch(
        cbv_initial,
        cbv_config,
        max_steps=100,
    )

    assert cbv_result.stop_reason is BatchStopReason.EVALUATOR_BUDGET


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
@pytest.mark.parametrize(
    "source",
    [
        (
            "onlyNil [] = 0\n"
            "main = onlyNil [7]"
        ),
        (
            "onlyCons (h:t) = 1\n"
            "main = onlyCons []"
        ),
        (
            "onlyNil [] = 0\n"
            "main = onlyNil True"
        ),
    ],
)
def test_non_exhaustive_patterns_raise_explicit_error(
    strategy,
    source,
):
    config = replace(
        make_config(strategy=strategy),
        execution_step_limit=200,
    )

    initial = create_initial_core_state(
        compile_source(source),
        config,
        session_id="non-exhaustive-case",
    )

    with pytest.raises(
        PatternMatchError,
        match="Non-exhaustive CoreCase",
    ):
        run_batch(initial, config, max_steps=200)


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
@pytest.mark.parametrize(
    "source, expected",
    [
        (
            "inner [] = 10\n"
            "inner (h:t) = h\n"
            "outer [] = 0\n"
            "outer (h:t) = inner t\n"
            "main = outer [1, 2]",
            2,
        ),
        (
            "choose [] = \\ignored -> 0\n"
            "choose (h:t) = \\ignored -> h\n"
            "main = (choose [(1 + 2)]) 0",
            3,
        ),
    ],
)
def test_case_nested_scopes_and_escaping_closures(
    strategy,
    source,
    expected,
):
    config = replace(
        make_config(strategy=strategy),
        execution_step_limit=400,
    )

    initial = create_initial_core_state(
        compile_source(source),
        config,
        session_id="case-scope-regression",
    )

    result = run_batch(
        initial,
        config,
        max_steps=400,
    )

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    machine = result.state.machine_state

    assert machine.control == Return(
        ImmediateInteger(expected)
    )

    assert machine.stack.depth == 0