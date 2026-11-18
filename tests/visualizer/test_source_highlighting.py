
"""Tests for passive source highlighting metadata."""

import json
from dataclasses import asdict, replace

import pytest

from lazy_lab.core.nodes import (
    CoreBinding,
    CoreInt,
    CoreProgram,
)
from lazy_lab.runtime.control import EvaluateCore, Return
from lazy_lab.runtime.references import ImmediateInteger
from lazy_lab.runtime.state import (
    ExecutionConfig,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.source import OriginKind, SourceSpan
from lazy_lab.visualizer.session import create_interactive_session
from lazy_lab.visualizer.source_highlighting import (
    project_source_highlighting,
)
from tests.helpers.runtime_equivalence import runtime_fingerprint


def make_session(source="main = 1 + 2"):
    config = ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=100,
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


def test_source_expression_has_direct_highlight():
    session = make_session()
    expression = session.core_program.bindings[0].rhs

    state = with_control(
        session.live_state,
        EvaluateCore(expression),
    )

    projection = project_source_highlighting(
        state,
        session.core_program,
    )

    assert projection["active"]["resolution"] == "resolved"
    assert projection["active"]["core_node_id"] == (
        "core/bindings/0/rhs"
    )

    assert expression.span is not None

    assert projection["provenance"] == {
        "origin": "SOURCE",
        "span": asdict(expression.span),
    }

    assert projection["highlight"] == {
        "mode": "direct",
        "span": asdict(expression.span),
        "reason": None,
    }

    json.dumps(projection, allow_nan=False)


def test_generated_constructor_uses_context_highlight():
    session = make_session("main = [1, 2]")
    expression = session.core_program.bindings[0].rhs

    assert expression.origin is OriginKind.GENERATED
    assert expression.span is not None

    state = with_control(
        session.live_state,
        EvaluateCore(expression),
    )

    projection = project_source_highlighting(
        state,
        session.core_program,
    )

    assert projection["active"]["resolution"] == "resolved"
    assert projection["provenance"]["origin"] == "GENERATED"

    assert projection["highlight"] == {
        "mode": "context",
        "span": asdict(expression.span),
        "reason": "generated_core",
    }


def test_missing_span_does_not_invent_coordinates():
    expression = CoreInt(
        42,
        origin=OriginKind.SOURCE,
    )

    program = CoreProgram(
        bindings=(
            CoreBinding(
                name="main",
                rhs=expression,
            ),
        ),
    )

    session = make_session("main = 42")

    state = with_control(
        session.live_state,
        EvaluateCore(expression),
    )

    projection = project_source_highlighting(state, program)

    assert projection["active"]["resolution"] == "resolved"
    assert projection["provenance"] == {
        "origin": "SOURCE",
        "span": None,
    }

    assert projection["highlight"] == {
        "mode": "none",
        "span": None,
        "reason": "missing_span",
    }


@pytest.mark.parametrize(
    "origin",
    [OriginKind.INTERNAL, OriginKind.UNKNOWN],
)
def test_non_source_origin_is_not_highlighted(origin):
    expression = CoreInt(
        42,
        origin=origin,
        span=SourceSpan(1, 8, 1, 10),
    )

    program = CoreProgram(
        bindings=(
            CoreBinding(
                name="main",
                rhs=expression,
            ),
        ),
    )

    session = make_session("main = 42")

    state = with_control(
        session.live_state,
        EvaluateCore(expression),
    )

    projection = project_source_highlighting(state, program)

    assert projection["active"]["resolution"] == "resolved"
    assert projection["provenance"]["origin"] == origin.value

    assert projection["highlight"] == {
        "mode": "none",
        "span": None,
        "reason": "non_source_origin",
    }


def test_unmapped_expression_cannot_be_highlighted():
    session = make_session("main = 42")

    independent = CoreInt(
        42,
        span=SourceSpan(1, 8, 1, 10),
        origin=OriginKind.SOURCE,
    )

    state = with_control(
        session.live_state,
        EvaluateCore(independent),
    )

    projection = project_source_highlighting(
        state,
        session.core_program,
    )

    assert projection["active"]["resolution"] == "unmapped"
    assert projection["provenance"] is None
    assert projection["highlight"] == {
        "mode": "none",
        "span": None,
        "reason": "unmapped",
    }


def test_return_control_has_no_source_highlight():
    session = make_session()

    state = with_control(
        session.live_state,
        Return(ImmediateInteger(42)),
    )

    projection = project_source_highlighting(
        state,
        session.core_program,
    )

    assert projection["active"]["resolution"] == "no_expression"
    assert projection["provenance"] is None

    assert projection["highlight"] == {
        "mode": "none",
        "span": None,
        "reason": "no_expression",
    }


def test_highlighting_is_passive_and_deterministic():
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

    first = project_source_highlighting(
        state,
        session.core_program,
    )
    second = project_source_highlighting(
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
        project_source_highlighting(
            None,
            session.core_program,
        )

    with pytest.raises(TypeError, match="CoreProgram"):
        project_source_highlighting(
            session.live_state,
            None,
        )
