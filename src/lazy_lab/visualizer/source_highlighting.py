
"""Passive source highlighting metadata for active Core nodes."""

from __future__ import annotations

from dataclasses import asdict

from lazy_lab.core.nodes import CoreExpr, CoreProgram
from lazy_lab.runtime.control import ApplyPrimitive, EvaluateCore
from lazy_lab.runtime.state import ExecutionState
from lazy_lab.source import OriginKind
from lazy_lab.visualizer.active_expression import (
    project_active_core_expression,
)


def project_source_highlighting(
    state: ExecutionState,
    program: CoreProgram,
) -> dict[str, object]:
    """Describe source highlighting for the active Core expression.

    The projection preserves existing source coordinates and
    provenance. It never evaluates runtime references.
    """
    active = project_active_core_expression(state, program)

    result: dict[str, object] = {
        "active": active,
        "provenance": None,
        "highlight": {
            "mode": "none",
            "span": None,
            "reason": active["resolution"],
        },
    }

    if active["resolution"] != "resolved":
        return result

    control = state.machine_state.control

    if isinstance(control, EvaluateCore):
        expression: CoreExpr | None = control.expression

    elif isinstance(control, ApplyPrimitive):
        expression = control.primitive

    else:
        expression = None

    if expression is None:
        # Defensive fallback: a resolved node must have
        # an associated Core expression.
        raise RuntimeError(
            "Resolved Core node has no active expression"
        )

    span = (
        asdict(expression.span)
        if expression.span is not None
        else None
    )

    result["provenance"] = {
        "origin": expression.origin.value,
        "span": span,
    }

    if span is None:
        result["highlight"] = {
            "mode": "none",
            "span": None,
            "reason": "missing_span",
        }

    elif expression.origin is OriginKind.SOURCE:
        result["highlight"] = {
            "mode": "direct",
            "span": span,
            "reason": None,
        }

    elif expression.origin is OriginKind.GENERATED:
        result["highlight"] = {
            "mode": "context",
            "span": span,
            "reason": "generated_core",
        }

    else:
        result["highlight"] = {
            "mode": "none",
            "span": None,
            "reason": "non_source_origin",
        }

    return result
