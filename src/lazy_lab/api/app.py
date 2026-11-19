
"""Minimal FastAPI application for the Lazy Evaluation Lab."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, status

from lazy_lab.api.registry import (
    SessionNotFoundError,
    SessionRegistry,
)
from lazy_lab.api.schemas import SessionCreateRequest
from lazy_lab.runtime.state import (
    ExecutionConfig,
    MachineKind,
    Strategy,
)
from lazy_lab.visualizer.session import (
    create_interactive_session,
)
from lazy_lab.visualizer.session_projection import (
    project_interactive_session,
)


def create_app() -> FastAPI:
    """Create an isolated API application and session registry."""

    app = FastAPI(
        title="Lazy Evaluation Lab API",
        version="0.1.0",
    )

    app.state.registry = SessionRegistry()

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/api/sessions",
        status_code=status.HTTP_201_CREATED,
    )
    def create_session(
        request: SessionCreateRequest,
    ) -> dict[str, object]:
        """Create and inspect a session without executing it."""

        config = ExecutionConfig(
            machine_kind=MachineKind.CORE,
            strategy=Strategy(request.strategy),
            result_policy=request.result_policy,
            execution_step_limit=request.execution_step_limit,
            result_node_limit=request.result_node_limit,
            trace_mode=request.trace_mode,
        )

        try:
            session = create_interactive_session(
                request.source,
                config,
                entry=request.entry,
                capture_categories=request.capture_categories,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc

        # Project successfully before registering the session.
        projection = project_interactive_session(session)

        app.state.registry.add(session)

        return projection

    @app.get("/api/sessions/{session_id}")
    def inspect_session(
        session_id: str,
    ) -> dict[str, object]:
        """Read the selected state without advancing execution."""

        try:
            session = app.state.registry.get(session_id)
        except SessionNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=str(exc),
            ) from exc

        return project_interactive_session(session)

    return app

app = create_app()
