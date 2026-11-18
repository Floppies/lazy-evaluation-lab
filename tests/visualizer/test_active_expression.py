
"""Tests for passive active Core expression resolution."""

import json
from dataclasses import replace

import pytest

from lazy_lab.core.nodes import (
    CoreBinding,
    CoreInt,
    CorePrimOp,
    CoreProgram,
    CoreVar,
)
from lazy_lab.runtime.control import (
    ApplyPrimitive,
    EvaluateCore,
    Force,
    Return,
)
from lazy_lab.runtime.references import (
    HeapReference,
    ImmediateInteger,
    ObjectId,
)
from lazy_lab.runtime.state import (
    ExecutionConfig,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.visualizer.active_expression import (
    project_active_core_expression,
)
from lazy_lab.visualizer.session import (
    create_interactive_session,
    step_interactive_session,
)
from lazy_lab.visualizer.source_core import (
    find_core_node_ids,
)
from tests.helpers.runtime_equivalence import runtime_fingerprint


def make_session(source="main = 1 + 2"):
    config = ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=200,
        result_node_limit=100,
        trace_mode=TraceMode.FULL,
    )
    return create_interactive_session(source, config)


def with_control(state, control):
    return replace(
        state,
        machine_state=replace(
            state.machine_state,
            control=control,
        ),
    )


def test_equal_expressions_have_distinct_core_node_ids():
    session = make_session("main = 1 + 1")
    primitive = session.core_program.bindings[0].rhs

    assert isinstance(primitive, CorePrimOp)

    left, right = primitive.arguments

    assert left == right
    assert left is not right

    expected = (
        "core/bindings/0/rhs/arguments/0",
        "core/bindings/0/rhs/arguments/1",
    )

    actual = []

    for expression in (left, right):
        state = with_control(
            session.live_state,
            EvaluateCore(expression),
        )

        projection = project_active_core_expression(
            state,
            session.core_program,
        )

        assert projection["resolution"] == "resolved"
        actual.append(projection["core_node_id"])

    assert tuple(actual) == expected


def test_real_evaluator_exposes_active_core_expression():
    session = make_session()
    expected_id = "core/bindings/0/rhs/arguments/0"

    for _ in range(100):
        projection = project_active_core_expression(
            session.live_state,
            session.core_program,
        )

        if projection["core_node_id"] == expected_id:
            assert projection["control_kind"] == "EvaluateCore"
            assert projection["expression_kind"] == "CoreInt"
            assert projection["resolution"] == "resolved"
            json.dumps(projection, allow_nan=False)
            return

        previous_index = session.live_state.transition_index
        step_interactive_session(session)

        if session.live_state.transition_index == previous_index:
            break

    pytest.fail("Evaluator did not reach the expected Core expression")


def test_apply_primitive_uses_original_core_node():
    session = make_session()
    primitive = session.core_program.bindings[0].rhs

    state = with_control(
        session.live_state,
        ApplyPrimitive(
            operator="+",
            arguments=(
                ImmediateInteger(1),
                ImmediateInteger(2),
            ),
            primitive=primitive,
        ),
    )

    projection = project_active_core_expression(
        state,
        session.core_program,
    )

    assert projection == {
        "control_kind": "ApplyPrimitive",
        "expression_kind": "CorePrimOp",
        "core_node_id": "core/bindings/0/rhs",
        "resolution": "resolved",
    }


@pytest.mark.parametrize(
    "control",
    [
        Return(ImmediateInteger(42)),
        Force(HeapReference(ObjectId(99))),
    ],
)
def test_controls_without_core_expression_are_explicit(control):
    session = make_session()

    state = with_control(session.live_state, control)

    projection = project_active_core_expression(
        state,
        session.core_program,
    )

    assert projection["core_node_id"] is None
    assert projection["expression_kind"] is None
    assert projection["resolution"] == "no_expression"


def test_structurally_equal_unmapped_expression_is_not_guessed():
    session = make_session("main = 42")

    original = session.core_program.bindings[0].rhs
    independent = CoreInt(42)

    assert original == independent
    assert original is not independent

    state = with_control(
        session.live_state,
        EvaluateCore(independent),
    )

    projection = project_active_core_expression(
        state,
        session.core_program,
    )

    assert projection["expression_kind"] == "CoreInt"
    assert projection["core_node_id"] is None
    assert projection["resolution"] == "unmapped"


def test_synthetic_entry_expression_is_unmapped():
    session = make_session("main = 42")

    state = with_control(
        session.live_state,
        EvaluateCore(CoreVar("main")),
    )

    projection = project_active_core_expression(
        state,
        session.core_program,
    )

    assert projection["expression_kind"] == "CoreVar"
    assert projection["resolution"] == "unmapped"
    assert projection["core_node_id"] is None


def test_shared_core_node_instance_is_ambiguous():
    shared = CoreInt(7)

    program = CoreProgram(
        bindings=(
            CoreBinding(
                name="main",
                rhs=CorePrimOp(
                    operator="+",
                    arguments=(shared, shared),
                ),
            ),
        ),
    )

    matches = find_core_node_ids(program, shared)

    assert matches == (
        "core/bindings/0/rhs/arguments/0",
        "core/bindings/0/rhs/arguments/1",
    )

    session = make_session()

    state = with_control(
        session.live_state,
        EvaluateCore(shared),
    )

    projection = project_active_core_expression(
        state,
        program,
    )

    assert projection["resolution"] == "ambiguous"
    assert projection["core_node_id"] is None


def test_resolution_is_passive_and_deterministic():
    session = make_session()

    expression = session.core_program.bindings[0].rhs
    state = with_control(
        session.live_state,
        EvaluateCore(expression),
    )

    before = runtime_fingerprint(state)
    original_heap = state.machine_state.heap
    original_stack = state.machine_state.stack
    original_metrics = state.instrumentation_state

    first = project_active_core_expression(
        state,
        session.core_program,
    )
    second = project_active_core_expression(
        state,
        session.core_program,
    )

    assert first == second
    assert runtime_fingerprint(state) == before
    assert state.machine_state.heap is original_heap
    assert state.machine_state.stack is original_stack
    assert state.instrumentation_state is original_metrics


def test_invalid_arguments_are_rejected():
    session = make_session()

    with pytest.raises(TypeError, match="ExecutionState"):
        project_active_core_expression(
            None,
            session.core_program,
        )

    with pytest.raises(TypeError, match="CoreProgram"):
        project_active_core_expression(
            session.live_state,
            None,
        )
