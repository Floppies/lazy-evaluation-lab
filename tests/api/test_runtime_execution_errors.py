"""Regression tests for expected program failures at the HTTP boundary."""

import pytest
from fastapi.testclient import TestClient

from lazy_lab.api import app as api_module
from lazy_lab.api.app import create_app
from lazy_lab.runtime.state import ExecutionStatus
from lazy_lab.visualizer.session import request_auto_run


@pytest.mark.parametrize(
    "source, strategy, message",
    [
        ("main = 1 2", "CBNEED", "Cannot apply a non-function value"),
        ("main = [] 2", "CBV", "Cannot apply a non-function value"),
        (
            "main = True + 1",
            "CBNEED",
            "Primitive '+' requires integer operands",
        ),
        (
            "main = True == 1",
            "CBNEED",
            "Primitive '==' requires operands of the same primitive type",
        ),
        (
            "main = if 1 then 2 else 3",
            "CBNEED",
            "If condition must evaluate to a Boolean",
        ),
        (
            "onlyCons (h:t) = h\nmain = onlyCons []",
            "CBNEED",
            "Non-exhaustive CoreCase: no alternative matches",
        ),
        (
            "main = let { x = x } in x",
            "CBV",
            "Local binding 'x' is uninitialized: strict evaluation "
            "demanded it before its RHS was installed",
        ),
    ],
)
def test_program_errors_pause_execution_and_preserve_last_valid_state(
    source, strategy, message,
):
    app = create_app()
    expected = {
        "detail": {
            "code": "runtime_execution_error",
            "message": message,
        },
    }

    with TestClient(app) as client:
        created = client.post(
            "/api/sessions",
            json={"source": source, "strategy": strategy},
        )
        assert created.status_code == 201
        session_id = created.json()["navigation"]["session_id"]
        session = app.state.registry.get(session_id)
        path = f"/api/sessions/{session_id}"

        failed = client.post(f"{path}/run", json={"max_steps": 100})
        assert failed.status_code == 409
        assert failed.json() == expected
        assert not session.auto_run_requested

        # Valid transitions preceding the failure remain retained.
        last_valid = session.live_state
        index = last_valid.transition_index
        assert index > 0
        assert last_valid.machine_state.status is ExecutionStatus.RUNNING
        assert session.history.available_indices == tuple(range(index + 1))
        inspected = client.get(path)
        assert inspected.status_code == 200
        projection = inspected.json()
        assert projection["execution"]["transition_index"] == index

        for command in ("step", "run"):
            request_auto_run(session)
            failed = client.post(
                f"{path}/{command}",
                **({"json": {"max_steps": 100}} if command == "run" else {}),
            )
            assert failed.status_code == 409
            assert failed.json() == expected
            assert not session.auto_run_requested
            assert session.live_state is last_valid
            assert session.history.available_indices == tuple(range(index + 1))
            # Covers heap, stack, metrics, cursor, and absence of synthetic work.
            assert client.get(path).json() == projection


@pytest.mark.parametrize(
    "command, operation",
    [("step", "step_interactive_session"), ("run", "run_interactive_batch")],
)
def test_internal_type_errors_are_not_reported_as_program_errors(
    monkeypatch, command, operation,
):
    app = create_app()

    def fail_internally(*args, **kwargs):
        raise TypeError("Internal implementation defect")

    with TestClient(app) as client:
        created = client.post("/api/sessions", json={"source": "main = 42"})
        session_id = created.json()["navigation"]["session_id"]
        monkeypatch.setattr(api_module, operation, fail_internally)

        with pytest.raises(TypeError, match="Internal implementation defect"):
            client.post(
                f"/api/sessions/{session_id}/{command}",
                **({"json": {"max_steps": 1}} if command == "run" else {}),
            )
