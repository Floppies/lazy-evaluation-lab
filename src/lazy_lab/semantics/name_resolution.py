from __future__ import annotations

from lazy_lab.ast import nodes as surface
from lazy_lab.source import SourceSpan


class NameResolutionError(ValueError):
    """Raised when a variable reference cannot be resolved."""

    def __init__(
        self,
        message: str,
        span: SourceSpan | None = None,
    ) -> None:
        self.span = span

        if span is not None:
            message = (
                f"{span.start_line}:{span.start_col}: {message}"
            )

        super().__init__(message)


def check_surface_names(
    program: surface.Program,
) -> None:
    """Check lexical references in a validated Surface program."""
    raise NotImplementedError(
        "Surface name checking is not implemented yet"
    )