"""Regression tests for complete, iterative HTTP response serialization."""

import pytest
from fastapi.testclient import TestClient

from lazy_lab.api import app as api_module
from lazy_lab.api.app import create_app
from lazy_lab.runtime.state import ExecutionStatus
from lazy_lab.visualizer.session import (
    create_interactive_session,
    run_interactive_batch,
)


def test_deep_materialized_list_is_returned_by_run_and_inspection():
    app = create_app()
    source = "main = [" + ",".join(str(i) for i in range(60)) + "]"

    with TestClient(app) as client:
        created = client.post(
            "/api/sessions",
            json={
                "source": source,
                "strategy": "CBNEED",
                "trace_mode": "METRICS_ONLY",
                "result_policy": "MATERIALIZE_COMPLETE_VALUE",
                "execution_step_limit": 20000,
                "result_node_limit": 1000,
            },
        )
        assert created.status_code == 201
        session_id = created.json()["navigation"]["session_id"]
        session = app.state.registry.get(session_id)
        path = f"/api/sessions/{session_id}"
        reference = create_interactive_session(source, session.config)

        for _ in range(3):
            executed = client.post(f"{path}/run", json={"max_steps": 1000})
            assert executed.status_code == 200
            assert executed.headers["content-type"] == "application/json"
            data = executed.json()
            expected = run_interactive_batch(reference, max_steps=1000)
            assert data["command"]["stop_reason"] == expected.stop_reason.value
            assert session.live_state.transition_index == (
                reference.live_state.transition_index
            )
            assert session.live_state.instrumentation_state == (
                reference.live_state.instrumentation_state
            )
            if session.live_state.machine_state.status is ExecutionStatus.COMPLETED:
                break
        else:
            pytest.fail("Materialization did not complete within three batches")

        projection = data["projection"]
        assert projection["metrics_result"]["result"]["available"]
        value = projection["metrics_result"]["result"]["canonical"]
        for i in range(60):
            assert value["kind"] == "constructor"
            assert value["tag"] == "Cons"
            head, value = value["fields"]
            assert head == {"kind": "integer", "value": i}
        assert value == {"kind": "constructor", "tag": "Nil", "fields": []}

        last_valid = session.live_state
        inspected = client.get(path)
        assert inspected.status_code == 200
        assert inspected.json() == projection
        assert session.live_state is last_valid


@pytest.mark.parametrize("command", ["create", "reset"])
def test_serialization_failure_preserves_registry(monkeypatch, command):
    app = create_app()

    def fail_serialization(payload):
        raise ValueError("Response serialization failed")

    with TestClient(app) as client:
        if command == "reset":
            created = client.post("/api/sessions", json={"source": "main = 42"})
            session_id = created.json()["navigation"]["session_id"]
            original = app.state.registry.get(session_id)
            path = f"/api/sessions/{session_id}/reset"
        else:
            path = "/api/sessions"

        with monkeypatch.context() as patch:
            patch.setattr(api_module, "json_dumps_iterative", fail_serialization)
            with pytest.raises(ValueError, match="Response serialization failed"):
                client.post(
                    path,
                    **({"json": {"source": "main = 42"}} if command == "create" else {}),
                )

        if command == "reset":
            assert len(app.state.registry) == 1
            assert app.state.registry.get(session_id) is original
            assert client.get(f"/api/sessions/{session_id}").json() == created.json()
        else:
            assert len(app.state.registry) == 0
