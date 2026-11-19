
"""Tests for session creation and passive HTTP inspection."""

import json

import pytest
from fastapi.testclient import TestClient

from lazy_lab.api.app import create_app
from tests.helpers.runtime_equivalence import runtime_fingerprint


SOURCE = "main = let { x = 1 + 2 } in x + x"


def payload(**overrides):
    result = {
        "source": SOURCE,
        "strategy": "CBNEED",
        "result_policy": "WHNF_ONLY",
        "trace_mode": "FULL",
        "execution_step_limit": 500,
        "result_node_limit": 100,
        "entry": "main",
    }
    result.update(overrides)
    return result


@pytest.mark.parametrize("strategy", ["CBV", "CBNEED"])
def test_create_session_returns_initial_projection(strategy):
    app = create_app()

    with TestClient(app) as client:
        response = client.post(
            "/api/sessions",
            json=payload(strategy=strategy),
        )

    assert response.status_code == 201

    projection = response.json()
    navigation = projection["navigation"]

    assert navigation["read_cursor_index"] == 0
    assert navigation["live_transition_index"] == 0
    assert navigation["following_live_head"] is True

    assert projection["execution"]["config"]["strategy"] == (
        strategy
    )
    assert projection["execution"]["machine"]["status"] == (
        "RUNNING"
    )

    assert projection["source_core"]["source"] == SOURCE
    assert projection["memory"]["heap_table"]["cells"] == []

    session = app.state.registry.get(
        navigation["session_id"]
    )

    assert session.live_state.transition_index == 0
    assert len(app.state.registry) == 1

    json.dumps(projection, allow_nan=False)


def test_get_session_is_passive_and_deterministic():
    app = create_app()

    with TestClient(app) as client:
        created = client.post(
            "/api/sessions",
            json=payload(),
        )

        session_id = created.json()["navigation"]["session_id"]
        session = app.state.registry.get(session_id)

        before = runtime_fingerprint(session.live_state)
        cursor_before = session.read_cursor_index
        history_before = session.history.snapshot_count

        first = client.get(f"/api/sessions/{session_id}")
        second = client.get(f"/api/sessions/{session_id}")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json() == created.json()

    assert runtime_fingerprint(session.live_state) == before
    assert session.read_cursor_index == cursor_before
    assert session.history.snapshot_count == history_before


def test_unknown_session_returns_404():
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/api/sessions/missing")

    assert response.status_code == 404
    assert "Session not found" in response.json()["detail"]


def test_invalid_source_does_not_register_session():
    app = create_app()

    with TestClient(app) as client:
        response = client.post(
            "/api/sessions",
            json=payload(source="main ="),
        )

    assert response.status_code == 422
    assert len(app.state.registry) == 0


@pytest.mark.parametrize(
    "invalid",
    [
        {"strategy": "CBN"},
        {"execution_step_limit": 0},
        {"result_node_limit": -1},
        {"trace_mode": "INVALID"},
        {"machine_kind": "STG"},
    ],
)
def test_invalid_request_is_rejected(invalid):
    app = create_app()

    with TestClient(app) as client:
        response = client.post(
            "/api/sessions",
            json=payload(**invalid),
        )

    assert response.status_code == 422
    assert len(app.state.registry) == 0


def test_capture_categories_require_events_mode():
    app = create_app()

    with TestClient(app) as client:
        invalid = client.post(
            "/api/sessions",
            json=payload(
                trace_mode="FULL",
                capture_categories=["thunks"],
            ),
        )

        valid = client.post(
            "/api/sessions",
            json=payload(
                trace_mode="EVENTS",
                capture_categories=["thunks"],
            ),
        )

    assert invalid.status_code == 422
    assert valid.status_code == 201

    session_id = valid.json()["navigation"]["session_id"]
    session = app.state.registry.get(session_id)

    assert session.capture_categories == frozenset({"thunks"})


def test_application_registries_remain_independent():
    first_app = create_app()
    second_app = create_app()

    with TestClient(first_app) as client:
        created = client.post(
            "/api/sessions",
            json=payload(),
        )

    session_id = created.json()["navigation"]["session_id"]

    with TestClient(second_app) as client:
        response = client.get(f"/api/sessions/{session_id}")

    assert response.status_code == 404
    assert len(first_app.state.registry) == 1
    assert len(second_app.state.registry) == 0
