
"""Tests for FastAPI foundation and in-memory session registry."""

import pytest
from fastapi.testclient import TestClient

from lazy_lab.api.app import create_app
from lazy_lab.api.registry import (
    SessionNotFoundError,
    SessionRegistry,
)
from lazy_lab.runtime.state import (
    ExecutionConfig,
    MachineKind,
    ResultPolicy,
    Strategy,
    TraceMode,
)
from lazy_lab.visualizer.session import create_interactive_session


def make_session():
    config = ExecutionConfig(
        machine_kind=MachineKind.CORE,
        strategy=Strategy.CBNEED,
        result_policy=ResultPolicy.WHNF_ONLY,
        execution_step_limit=100,
        result_node_limit=100,
        trace_mode=TraceMode.FULL,
    )

    return create_interactive_session(
        "main = 42",
        config,
    )


def test_registry_starts_empty():
    registry = SessionRegistry()
    assert len(registry) == 0


def test_registry_stores_original_session():
    registry = SessionRegistry()
    session = make_session()

    registry.add(session)

    assert len(registry) == 1
    assert registry.get(session.session_id) is session


def test_registry_rejects_duplicate_ids():
    registry = SessionRegistry()
    session = make_session()

    registry.add(session)

    with pytest.raises(ValueError, match="already exists"):
        registry.add(session)


def test_registry_reports_unknown_session():
    registry = SessionRegistry()

    with pytest.raises(
        SessionNotFoundError,
        match="Session not found",
    ):
        registry.get("missing-session")


def test_registry_replaces_reset_session():
    registry = SessionRegistry()

    previous = make_session()
    replacement = make_session()

    registry.add(previous)
    registry.replace(previous.session_id, replacement)

    assert len(registry) == 1
    assert registry.get(replacement.session_id) is replacement

    with pytest.raises(SessionNotFoundError):
        registry.get(previous.session_id)


def test_registry_rejects_invalid_values():
    registry = SessionRegistry()

    with pytest.raises(TypeError, match="InteractiveSession"):
        registry.add(None)

    with pytest.raises(TypeError, match="Session ID"):
        registry.get(None)


def test_health_endpoint():
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(app.state.registry) == 0


def test_app_instances_have_isolated_registries():
    first_app = create_app()
    second_app = create_app()

    session = make_session()
    first_app.state.registry.add(session)

    assert len(first_app.state.registry) == 1
    assert len(second_app.state.registry) == 0


def test_openapi_contains_health_route():
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/api/health" in response.json()["paths"]
