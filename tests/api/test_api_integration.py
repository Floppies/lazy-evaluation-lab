
"""End-to-end HTTP integration tests for interactive sessions."""

import json

from fastapi.testclient import TestClient

from lazy_lab.api.app import create_app
from tests.helpers.runtime_equivalence import runtime_fingerprint


SOURCE = "main = let { x = 1 + 2 } in x + x"


def create_session(client, *, source=SOURCE, **overrides):
    payload = {
        "source": source,
        "strategy": "CBNEED",
        "trace_mode": "FULL",
        "result_policy": "WHNF_ONLY",
        "execution_step_limit": 500,
        "result_node_limit": 100,
    }
    payload.update(overrides)

    response = client.post("/api/sessions", json=payload)

    assert response.status_code == 201

    projection = response.json()
    session_id = projection["navigation"]["session_id"]

    return session_id, projection


def test_full_session_lifecycle_and_historical_inspection():
    app = create_app()

    with TestClient(app) as client:
        session_id, initial = create_session(client)
        path = f"/api/sessions/{session_id}"

        assert initial["execution"]["transition_index"] == 0

        executed = client.post(
            f"{path}/run",
            json={"max_steps": 3},
        )

        assert executed.status_code == 200

        live_index = executed.json()["projection"][
            "navigation"
        ]["live_transition_index"]

        assert live_index == 3

        session = app.state.registry.get(session_id)
        fingerprint_before = runtime_fingerprint(
            session.live_state
        )

        # Navigate to a retained historical snapshot.
        selected = client.post(
            f"{path}/history/select",
            json={"transition_index": 1},
        )

        assert selected.status_code == 200
        assert selected.json()["projection"][
            "navigation"
        ]["read_cursor_index"] == 1

        inspected = client.get(path)

        assert inspected.status_code == 200
        assert inspected.json() == selected.json()["projection"]

        # Historical inspection did not alter live execution.
        assert runtime_fingerprint(
            session.live_state
        ) == fingerprint_before

        # Execution continues from live head, not read cursor.
        stepped = client.post(f"{path}/step")

        assert stepped.status_code == 200
        assert stepped.json()["command"][
            "transitions_executed"
        ] == 1

        nav = stepped.json()["projection"]["navigation"]

        assert nav["read_cursor_index"] == 1
        assert nav["live_transition_index"] == live_index + 1

        returned = client.post(f"{path}/history/live")

        assert returned.status_code == 200
        assert returned.json()["projection"][
            "navigation"
        ]["following_live_head"]

        # Reset invalidates the old session ID.
        reset = client.post(f"{path}/reset")

        assert reset.status_code == 200

        replacement = reset.json()["projection"]
        new_id = replacement["navigation"]["session_id"]

        assert new_id != session_id
        assert replacement["execution"]["transition_index"] == 0
        assert client.get(path).status_code == 404
        assert client.get(
            f"/api/sessions/{new_id}"
        ).status_code == 200

        json.dumps(replacement, allow_nan=False)


def test_ask_at_whnf_completes_through_http():
    app = create_app()

    with TestClient(app) as client:
        session_id, _ = create_session(
            client,
            source="main = 42",
            result_policy="ASK_AT_WHNF",
        )
        path = f"/api/sessions/{session_id}"

        pending = client.post(
            f"{path}/run",
            json={"max_steps": 100},
        )

        assert pending.status_code == 200
        assert pending.json()["command"][
            "stop_reason"
        ] == "WHNF_PENDING"

        selected = client.post(
            f"{path}/result-mode",
            json={"mode": "WHNF_ONLY"},
        )

        assert selected.status_code == 200
        assert selected.json()["command"]["rule_id"] == (
            "RESULT_SELECT_MODE"
        )

        finished = client.post(
            f"{path}/run",
            json={"max_steps": 100},
        )

        assert finished.status_code == 200

        projection = finished.json()["projection"]

        assert projection["execution"]["machine"]["status"] == (
            "COMPLETED"
        )
        assert projection["metrics_result"]["result"][
            "available"
        ] is True

        assert client.get(path).json() == projection


def test_events_capture_configuration_through_http():
    app = create_app()

    with TestClient(app) as client:
        session_id, _ = create_session(
            client,
            trace_mode="EVENTS",
        )
        path = f"/api/sessions/{session_id}"

        changed = client.post(
            f"{path}/capture-filters",
            json={"categories": ["thunks", "heap"]},
        )

        assert changed.status_code == 200

        inspected = client.get(path)

        assert inspected.status_code == 200
        assert inspected.json()["navigation"][
            "capture_categories"
        ] == ["heap", "thunks"]

        executed = client.post(
            f"{path}/run",
            json={"max_steps": 2},
        )

        assert executed.status_code == 200

        session = app.state.registry.get(session_id)

        assert session.live_state.transition_index == 2
        assert session.capture_categories == frozenset({
            "heap",
            "thunks",
        })

        # The response is still JSON-compatible.
        json.dumps(executed.json(), allow_nan=False)
