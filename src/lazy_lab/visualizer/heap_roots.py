
"""Passive projection of references held by machine roots."""

from __future__ import annotations

from dataclasses import fields

from lazy_lab.runtime.environment import Environment
from lazy_lab.runtime.references import HeapReference
from lazy_lab.runtime.state import ExecutionState


def _add_root(
    roots: list[dict[str, object]],
    source: str,
    role: str,
    reference: object,
) -> None:
    """Record a heap reference without dereferencing it."""

    if not isinstance(reference, HeapReference):
        return

    roots.append({
        "root_id": f"{source}.{role}",
        "source": source,
        "role": role,
        "target_object_id": int(reference.object_id),
    })

def _collect_environment(
    environment: Environment,
    source: str,
    prefix: str,
    roots: list[dict[str, object]],
) -> None:
    """Collect bindings from every retained lexical scope."""

    current: Environment | None = environment
    depth = 0

    while current is not None:
        for name, reference in sorted(
            current.bindings.items()
        ):
            _add_root(
                roots,
                source,
                f"{prefix}.scope[{depth}].{name}",
                reference,
            )

        current = current.parent
        depth += 1

def _collect_record_fields(
    record: object,
    source: str,
    prefix: str,
    roots: list[dict[str, object]],
) -> None:
    """Collect direct references and environment fields.

    Core syntax trees and unrelated nested dataclasses are
    deliberately not traversed.
    """

    for item in fields(record):
        value = getattr(record, item.name)

        role = (
            f"{prefix}.{item.name}"
            if prefix
            else item.name
        )

        if isinstance(value, Environment):
            _collect_environment(
                value,
                source,
                role,
                roots,
            )

        elif isinstance(value, HeapReference):
            _add_root(
                roots,
                source,
                role,
                value,
            )

        elif isinstance(value, tuple):
            for index, reference in enumerate(value):
                _add_root(
                    roots,
                    source,
                    f"{role}[{index}]",
                    reference,
                )

def project_memory_roots(
    state: ExecutionState,
) -> dict[str, object]:
    """Project references retained outside simulated heap cells."""

    if not isinstance(state, ExecutionState):
        raise TypeError("Expected an ExecutionState")

    machine = state.machine_state
    roots: list[dict[str, object]] = []

    _collect_environment(
        machine.local_environment,
        "local_environment",
        "bindings",
        roots,
    )

    _collect_environment(
        machine.global_environment,
        "global_environment",
        "bindings",
        roots,
    )

    _collect_record_fields(
        machine.control,
        "control",
        "",
        roots,
    )

    # Stack frames are ordered from bottom to top.
    for index, frame in enumerate(machine.stack.frames):
        _collect_record_fields(
            frame,
            "stack",
            f"frames[{index}]",
            roots,
        )

    result = machine.result_state

    _collect_record_fields(
        result,
        "result_state",
        "",
        roots,
    )

    # Result materialization has its own continuation frames.
    materialization = result.materialization

    if materialization is not None:
        _collect_record_fields(
            materialization,
            "result_state",
            "materialization",
            roots,
        )

        for index, frame in enumerate(
            materialization.frames
        ):
            _collect_record_fields(
                frame,
                "result_state",
                f"materialization.frames[{index}]",
                roots,
            )

    return {
        "transition_index": state.transition_index,
        "root_count": len(roots),
        "roots": roots,
    }
