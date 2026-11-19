
"""Minimal FastAPI application for the Lazy Evaluation Lab."""

from __future__ import annotations

from fastapi import FastAPI

from lazy_lab.api.registry import SessionRegistry


def create_app() -> FastAPI:
    """Create an isolated API application and session registry."""

    app = FastAPI(
        title="Lazy Evaluation Lab API",
        version="0.1.0",
    )

    app.state.registry = SessionRegistry()

    @app.get("/api/health")
    def health() -> dict[str, str]:
        """Report that the HTTP application is responding."""
        return {"status": "ok"}

    return app


app = create_app()
