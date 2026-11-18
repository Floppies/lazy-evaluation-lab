
"""Integration tests for Source/Core session projections."""

import json

import pytest

from lazy_lab.runtime.state import (
    ExecutionConfig,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.visualizer.session import (
    create_interactive_session,
    follow_live_head,
    run_interactive_batch,
    select_historical_state,
    step_interactive_session,
)
from lazy_lab.visualizer.session_projection import (
    project_interactive_session,
)
from tests.helpers.runtime_equivalence import runtime_fingerprint


def make_session(
    source="main = 1 + 2",
    *,
    strategy=Strategy.CBNEED,
    mode=TraceMode.FULL,
):
    config = ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=strategy,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=500,
        result_node_limit=100,
        trace_mode=mode,
    )

    return create_interactive_session(source, config)


def find_projection(session, predicate, max_steps=200):
    """Advance until a projected state satisfies a condition."""

    for _ in range(max_steps):
        projection = project_interactive_session(session)

        if predicate(projection):
            return projection

        before = session.live_state.transition_index
        step_interactive_session(session)

        if session.live_state.transition_index == before:
            break

    pytest.fail("Expected projected state was not reached")


def test_initial_projection_contains_source_and_core():
    session = make_session("main = 42")

    projection = project_interactive_session(session)

    assert projection["source_core"]["source"] == "main = 42"
    assert projection["source_core"]["core"]["root_id"] == "core"

    nodes = {
        node["node_id"]: node
        for node in projection["source_core"]["core"]["nodes"]
    }

    assert nodes["core/bindings/0"]["attributes"]["name"] == "main"
    assert nodes["core/bindings/0/rhs"]["kind"] == "CoreInt"

    # Initialization has no active Core expression.
    assert projection["source_highlighting"]["active"][
        "resolution"
    ] == "no_expression"

    assert projection["source_highlighting"]["highlight"][
        "mode"
    ] == "none"

    json.dumps(projection, allow_nan=False)


@pytest.mark.parametrize(
    "strategy",
    [Strategy.CBV, Strategy.CBNEED],
)
def test_active_expression_matches_static_core_tree(strategy):
    session = make_session(strategy=strategy)

    target_id = "core/bindings/0/rhs/arguments/0"

    projection = find_projection(
        session,
        lambda p: (
            p["source_highlighting"]["active"]["core_node_id"]
            == target_id
        ),
    )

    highlight = projection["source_highlighting"]

    assert highlight["active"]["resolution"] == "resolved"
    assert highlight["active"]["expression_kind"] == "CoreInt"
    assert highlight["highlight"]["mode"] == "direct"

    nodes = {
        node["node_id"]: node
        for node in projection["source_core"]["core"]["nodes"]
    }

    assert target_id in nodes
    assert nodes[target_id]["kind"] == "CoreInt"
    assert nodes[target_id]["origin"] == "SOURCE"

    assert (
        highlight["highlight"]["span"]
        == nodes[target_id]["span"]
    )

    json.dumps(projection, allow_nan=False)


def test_generated_core_uses_context_highlighting():
    session = make_session("main = [1, 2]")

    projection = find_projection(
        session,
        lambda p: (
            p["source_highlighting"]["highlight"]["mode"]
            == "context"
        ),
    )

    highlight = projection["source_highlighting"]

    assert highlight["active"]["resolution"] == "resolved"
    assert highlight["provenance"]["origin"] == "GENERATED"
    assert highlight["highlight"]["reason"] == "generated_core"

    node_id = highlight["active"]["core_node_id"]

    nodes = {
        node["node_id"]: node
        for node in projection["source_core"]["core"]["nodes"]
    }

    assert nodes[node_id]["origin"] == "GENERATED"
    assert highlight["highlight"]["span"] == nodes[node_id]["span"]


def test_historical_cursor_projects_historical_highlight():
    session = make_session()

    target_id = "core/bindings/0/rhs/arguments/0"

    earlier = find_projection(
        session,
        lambda p: (
            p["source_highlighting"]["active"]["core_node_id"]
            == target_id
        ),
    )

    historical_index = earlier["execution"]["transition_index"]

    run_interactive_batch(session, max_steps=200)

    live_state = session.live_state
    live_index = live_state.transition_index

    assert live_index > historical_index

    select_historical_state(session, historical_index)

    historical = project_interactive_session(session)

    assert historical["navigation"]["read_cursor_index"] == (
        historical_index
    )
    assert historical["navigation"]["live_transition_index"] == (
        live_index
    )
    assert not historical["navigation"]["following_live_head"]

    assert historical["execution"]["transition_index"] == (
        historical_index
    )
    assert historical["source_highlighting"] == (
        earlier["source_highlighting"]
    )

    assert historical["source_core"] == earlier["source_core"]

    # Looking at the past must not replace the live head.
    assert session.live_state is live_state

    follow_live_head(session)

    current = project_interactive_session(session)

    assert current["navigation"]["following_live_head"]
    assert current["execution"]["transition_index"] == live_index


@pytest.mark.parametrize("mode", list(TraceMode))
def test_source_core_is_available_in_all_trace_modes(mode):
    session = make_session(mode=mode)

    run_interactive_batch(session, max_steps=5)

    projection = project_interactive_session(session)

    assert projection["source_core"]["source"] == "main = 1 + 2"
    assert projection["source_core"]["core"]["nodes"]

    assert (
        projection["execution"]["transition_index"]
        == projection["navigation"]["read_cursor_index"]
    )

    json.dumps(projection, allow_nan=False)


def test_source_session_projection_is_passive():
    session = make_session(
        "main = let { x = 1 + 2 } in x + x"
    )

    run_interactive_batch(session, max_steps=15)

    before = runtime_fingerprint(session.live_state)
    cursor_before = session.read_cursor_index
    snapshot_count = session.history.snapshot_count

    first = project_interactive_session(session)
    second = project_interactive_session(session)

    assert first == second

    assert runtime_fingerprint(session.live_state) == before
    assert session.read_cursor_index == cursor_before
    assert session.history.snapshot_count == snapshot_count


def test_invalid_session_is_rejected():
    with pytest.raises(TypeError, match="InteractiveSession"):
        project_interactive_session(None)
