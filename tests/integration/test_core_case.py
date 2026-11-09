import pytest

from lazy_lab.core.nodes import (
    CoreCase,
    CoreCon,
    CoreConAlt,
    CoreInt,
)
from lazy_lab.pipeline import compile_source
from lazy_lab.engine.core_machine import (
    create_initial_core_state,
    step,
)
from lazy_lab.runtime.control import EvaluateCore
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