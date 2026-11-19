
"""HTTP tests for historical navigation and capture filters."""

import pytest
from fastapi.testclient import TestClient

from lazy_lab.api.app import create_app
from tests.helpers.runtime_equivalence import runtime_fingerprint


SOURCE = "main = let { x = 1 + 2 } in x + x"


def create_session(client, *, mode="FULL"):
    response = client.post(
        "/api/sessions",
        json={
            "source": SOURCE,
            "strategy": "CBNEED",
            "trace_mode": mode,
            "result_policy": "WHNF_ONLY",
            "execution_step_limit": 500,
            "result_node_limit": 100,
        },
    )
    assert response.status_code == 201

    return response.json()["navigation"]["session_id"]


def test_select_history_and_return_to_live_head():
    app = create_app()

    with TestClient(app) as client:
        session_id = create_session(client)
        path = f"/api/sessions/{session_id}"

        executed = client.post(
            f"{path}/run",
            json={"max_steps": 5},
        )

        assert executed.status_code == 200

        session = app.state.registry.get(session_id)
        live_index = session.live_state.transition_index
        live_before = runtime_fingerprint(session.live_state)

        historical = client.post(
            f"{path}/history/select",
            json={"transition_index": 2},
        )

        assert historical.status_code == 200

        nav = historical.json()["projection"]["navigation"]

        assert nav["read_cursor_index"] == 2
        assert nav["live_transition_index"] == live_index
        assert not nav["following_live_head"]

        assert (
            historical.json()["projection"]["execution"][
                "transition_index"
            ] == 2
        )

        assert runtime_fingerprint(session.live_state) == live_before

        returned = client.post(f"{path}/history/live")

        assert returned.status_code == 200

        nav = returned.json()["projection"]["navigation"]

        assert nav["read_cursor_index"] == live_index
        assert nav["following_live_head"]
        assert runtime_fingerprint(session.live_state) == live_before


def test_missing_snapshot_preserves_cursor():
    app = create_app()

    with TestClient(app) as client:
        session_id = create_session(client, mode="METRICS_ONLY")
        path = f"/api/sessions/{session_id}"

        client.post(
            f"{path}/run",
            json={"max_steps": 5},
        )

        session = app.state.registry.get(session_id)
        cursor_before = session.read_cursor_index

        missing = client.post(
            f"{path}/history/select",
            json={"transition_index": 0},
        )

        assert missing.status_code == 404
        assert session.read_cursor_index == cursor_before

        live = client.post(f"{path}/history/live")
        assert live.status_code == 200


@pytest.mark.parametrize(
    "invalid",
    [-1, "2", True],
)
def test_invalid_history_index_returns_422(invalid):
    app = create_app()

    with TestClient(app) as client:
        session_id = create_session(client)

        response = client.post(
            f"/api/sessions/{session_id}/history/select",
            json={"transition_index": invalid},
        )

        assert response.status_code == 422


def test_events_capture_filters_update():
    app = create_app()

    with TestClient(app) as client:
        session_id = create_session(client, mode="EVENTS")
        path = f"/api/sessions/{session_id}"

        session = app.state.registry.get(session_id)

        assert session.capture_categories == frozenset()
        history_before = session.history.snapshot_count

        response = client.post(
            f"{path}/capture-filters",
            json={"categories": ["thunks", "heap"]},
        )

        assert response.status_code == 200
        assert response.json()["command"]["selected_categories"] == [
            "heap",
            "thunks",
        ]

        assert session.capture_categories == frozenset({
            "thunks",
            "heap",
        })

        # Filter changes do not retroactively capture states.
        assert session.history.snapshot_count == history_before
        assert session.live_state.transition_index == 0

        inspected = client.get(path)
        assert inspected.status_code == 200
        assert inspected.json()["navigation"]["capture_categories"] == [
            "heap",
            "thunks",
        ]


def test_capture_filters_reject_unknown_categories():
    app = create_app()

    with TestClient(app) as client:
        session_id = create_session(client, mode="EVENTS")
        path = f"/api/sessions/{session_id}/capture-filters"

        response = client.post(
            path,
            json={"categories": ["unknown-category"]},
        )

        assert response.status_code == 422

        session = app.state.registry.get(session_id)
        assert session.capture_categories == frozenset()


def test_capture_filters_require_events():
    app = create_app()

    with TestClient(app) as client:
        session_id = create_session(client, mode="FULL")

        response = client.post(
            f"/api/sessions/{session_id}/capture-filters",
            json={"categories": ["heap"]},
        )

        assert response.status_code == 409


def test_capture_filters_require_paused_run():
    app = create_app()

    with TestClient(app) as client:
        session_id = create_session(client, mode="EVENTS")
        path = f"/api/sessions/{session_id}"

        run = client.post(
            f"{path}/run",
            json={"max_steps": 1},
        )

        assert run.status_code == 200

        session = app.state.registry.get(session_id)
        assert session.auto_run_requested is True

        rejected = client.post(
            f"{path}/capture-filters",
            json={"categories": ["heap"]},
        )

        assert rejected.status_code == 409

        client.post(f"{path}/pause")

        accepted = client.post(
            f"{path}/capture-filters",
            json={"categories": ["heap"]},
        )

        assert accepted.status_code == 200
        assert session.capture_categories == frozenset({"heap"})


def test_unknown_session_returns_404():
    app = create_app()

    with TestClient(app) as client:
        response = client.post(
            "/api/sessions/missing/history/live"
        )

    assert response.status_code == 404
