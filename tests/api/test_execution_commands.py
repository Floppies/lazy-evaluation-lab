
"""HTTP tests for interactive execution commands."""

import pytest
from fastapi.testclient import TestClient

from lazy_lab.api.app import create_app


def create_session(
    client: TestClient,
    *,
    source: str = "main = 42",
    result_policy: str = "WHNF_ONLY",
) -> str:
    response = client.post(
        "/api/sessions",
        json={
            "source": source,
            "strategy": "CBNEED",
            "result_policy": result_policy,
            "trace_mode": "FULL",
            "execution_step_limit": 500,
            "result_node_limit": 100,
        },
    )
    assert response.status_code == 201
    return response.json()["navigation"]["session_id"]


def test_step_advances_one_transition():
    app = create_app()

    with TestClient(app) as client:
        session_id = create_session(client)

        response = client.post(
            f"/api/sessions/{session_id}/step"
        )

        assert response.status_code == 200

        data = response.json()

        assert data["command"]["kind"] == "step"
        assert data["command"]["transitions_executed"] == 1
        assert data["projection"]["execution"][
            "transition_index"
        ] == 1

        inspected = client.get(
            f"/api/sessions/{session_id}"
        )

        assert inspected.json() == data["projection"]


def test_run_is_bounded_and_pause_clears_request():
    app = create_app()

    with TestClient(app) as client:
        session_id = create_session(
            client,
            source="main = 1 + 2",
        )
        path = f"/api/sessions/{session_id}"

        response = client.post(
            f"{path}/run",
            json={"max_steps": 2},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["command"]["transitions_executed"] == 2
        assert data["command"]["stop_reason"] == "BATCH_LIMIT"
        assert data["projection"]["navigation"][
            "auto_run_requested"
        ] is True

        paused = client.post(f"{path}/pause")

        assert paused.status_code == 200
        assert paused.json()["command"]["kind"] == "pause"
        assert paused.json()["projection"]["navigation"][
            "auto_run_requested"
        ] is False
        assert paused.json()["projection"]["execution"][
            "transition_index"
        ] == 2


def test_reset_replaces_session_and_resets_state():
    app = create_app()

    with TestClient(app) as client:
        previous_id = create_session(client)
        previous_path = f"/api/sessions/{previous_id}"

        client.post(f"{previous_path}/step")

        response = client.post(f"{previous_path}/reset")

        assert response.status_code == 200
        data = response.json()

        new_id = data["projection"]["navigation"]["session_id"]

        assert new_id != previous_id
        assert data["command"]["previous_session_id"] == previous_id
        assert data["projection"]["execution"][
            "transition_index"
        ] == 0

        assert client.get(previous_path).status_code == 404
        assert client.get(
            f"/api/sessions/{new_id}"
        ).status_code == 200

        assert len(app.state.registry) == 1


def test_explicit_result_mode_at_whnf():
    app = create_app()

    with TestClient(app) as client:
        session_id = create_session(
            client,
            result_policy="ASK_AT_WHNF",
        )
        path = f"/api/sessions/{session_id}"

        run_response = client.post(
            f"{path}/run",
            json={"max_steps": 100},
        )

        assert run_response.status_code == 200
        assert run_response.json()["command"][
            "stop_reason"
        ] == "WHNF_PENDING"

        index_before = run_response.json()["projection"][
            "execution"
        ]["transition_index"]

        selected = client.post(
            f"{path}/result-mode",
            json={"mode": "WHNF_ONLY"},
        )

        assert selected.status_code == 200
        data = selected.json()

        assert data["command"]["rule_id"] == (
            "RESULT_SELECT_MODE"
        )
        assert data["command"]["transitions_executed"] == 1

        assert data["projection"]["execution"][
            "transition_index"
        ] == index_before + 1

        assert data["projection"]["execution"]["result"][
            "selected_mode"
        ] == "WHNF_ONLY"

        # A second selection must not silently overwrite it.
        repeated = client.post(
            f"{path}/result-mode",
            json={"mode": "MATERIALIZE_COMPLETE_VALUE"},
        )
        assert repeated.status_code == 409


def test_invalid_result_selection_returns_conflict():
    app = create_app()

    with TestClient(app) as client:
        session_id = create_session(client)
        path = f"/api/sessions/{session_id}"

        response = client.post(
            f"{path}/result-mode",
            json={"mode": "WHNF_ONLY"},
        )

        assert response.status_code == 409

        invalid_mode = client.post(
            f"{path}/result-mode",
            json={"mode": "CBV"},
        )

        assert invalid_mode.status_code == 422


@pytest.mark.parametrize(
    "max_steps",
    [0, -1, 1001, "10"],
)
def test_run_rejects_invalid_batch_size(max_steps):
    app = create_app()

    with TestClient(app) as client:
        session_id = create_session(client)

        response = client.post(
            f"/api/sessions/{session_id}/run",
            json={"max_steps": max_steps},
        )

        assert response.status_code == 422
        assert app.state.registry.get(
            session_id
        ).live_state.transition_index == 0


def test_terminal_run_is_rejected():
    app = create_app()

    with TestClient(app) as client:
        session_id = create_session(client)
        path = f"/api/sessions/{session_id}"

        completed = client.post(
            f"{path}/run",
            json={"max_steps": 100},
        )

        assert completed.status_code == 200
        assert completed.json()["projection"]["execution"][
            "machine"
        ]["status"] == "COMPLETED"

        rejected = client.post(
            f"{path}/run",
            json={"max_steps": 1},
        )

        assert rejected.status_code == 409


def test_unknown_session_command_returns_404():
    app = create_app()

    with TestClient(app) as client:
        response = client.post(
            "/api/sessions/nonexistent/step"
        )

    assert response.status_code == 404
