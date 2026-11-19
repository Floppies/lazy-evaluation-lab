
"""Minimal FastAPI application for the Lazy Evaluation Lab."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, status

from lazy_lab.api.registry import (
    SessionNotFoundError,
    SessionRegistry,
)
from lazy_lab.api.schemas import SessionCreateRequest, RunRequest, ResultModeRequest
from lazy_lab.runtime.state import (
    ExecutionConfig,
    MachineKind,
    Strategy,
    ResultPolicy,
)
from lazy_lab.visualizer.session import (
    InteractiveSession,
    create_interactive_session,
    pause_interactive_session,
    request_auto_run,
    reset_interactive_session,
    run_interactive_batch,
    select_interactive_result_mode,
    step_interactive_session,
)
from lazy_lab.visualizer.session_projection import (
    project_interactive_session,
)
from lazy_lab.engine.result_consumer import (
    InvalidResultObservationError,
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

    def _session_or_404(session_id: str) -> InteractiveSession:
        """Resolve a registered session for HTTP commands."""
        try:
            return app.state.registry.get(session_id)
        except SessionNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=str(exc),
            ) from exc

    def _command_response(
        session: InteractiveSession,
        command: str,
        **metadata: object,
    ) -> dict[str, object]:
        """Return command metadata and the synchronized projection."""
        return {
            "command": {
                "kind": command,
                **metadata,
            },
            "projection": project_interactive_session(session),
        }

    @app.post("/api/sessions/{session_id}/step")
    def step_session(session_id: str) -> dict[str, object]:
        """Execute at most one logical transition."""

        session = _session_or_404(session_id)

        # Manual stepping cancels automatic run requests.
        pause_interactive_session(session)

        before = session.live_state.transition_index
        result = step_interactive_session(session)

        return _command_response(
            session,
            "step",
            transitions_executed=(
                session.live_state.transition_index - before
            ),
            stop_reason=result.stop_reason.value,
        )

    @app.post("/api/sessions/{session_id}/run")
    def run_session(
        session_id: str,
        request: RunRequest,
    ) -> dict[str, object]:
        """Execute one bounded batch, never an unbounded loop."""

        session = _session_or_404(session_id)

        try:
            request_auto_run(session)
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail=str(exc),
            ) from exc

        before = session.live_state.transition_index

        result = run_interactive_batch(
            session,
            max_steps=request.max_steps,
        )

        return _command_response(
            session,
            "run",
            transitions_executed=(
                session.live_state.transition_index - before
            ),
            stop_reason=result.stop_reason.value,
        )

    @app.post("/api/sessions/{session_id}/pause")
    def pause_session(session_id: str) -> dict[str, object]:
        """Clear the automatic-run request flag."""

        session = _session_or_404(session_id)

        pause_interactive_session(session)

        return _command_response(session, "pause")

    @app.post("/api/sessions/{session_id}/reset")
    def reset_session(session_id: str) -> dict[str, object]:
        """Replace a session with a fresh run."""

        previous = _session_or_404(session_id)
        replacement = reset_interactive_session(previous)

        # Project before modifying the registry.
        response = _command_response(
            replacement,
            "reset",
            previous_session_id=session_id,
        )

        app.state.registry.replace(
            session_id,
            replacement,
        )

        return response

    @app.post("/api/sessions/{session_id}/result-mode")
    def choose_result_mode(
        session_id: str,
        request: ResultModeRequest,
    ) -> dict[str, object]:
        """Record an explicit result-mode selection at WHNF."""

        session = _session_or_404(session_id)

        try:
            transition = select_interactive_result_mode(
                session,
                ResultPolicy(request.mode),
            )
        except InvalidResultObservationError as exc:
            raise HTTPException(
                status_code=409,
                detail=str(exc),
            ) from exc

        return _command_response(
            session,
            "result-mode",
            transitions_executed=1,
            rule_id=transition.rule_id.value,
        )


    return app

app = create_app()
