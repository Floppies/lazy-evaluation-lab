
"""Passive structural projection of source code and Core IR."""

from __future__ import annotations

from dataclasses import fields

from lazy_lab.core.nodes import CoreNode, CoreProgram
from lazy_lab.source import SourceSpan


def _project_source_span(
    span: SourceSpan | None,
) -> dict[str, int] | None:
    """Preserve source coordinates without changing their semantics."""

    if span is None:
        return None

    return {
        "start_line": span.start_line,
        "start_column": span.start_column,
        "end_line": span.end_line,
        "end_column": span.end_column,
    }

def _describe_node(
    node: CoreNode,
    node_id: str,
) -> tuple[
    dict[str, object],
    tuple[tuple[str, CoreNode], ...],
]:
    """Describe one node and collect its structural children."""

    attributes: dict[str, object] = {}
    children: list[tuple[str, CoreNode]] = []

    for field_info in fields(node):
        name = field_info.name

        if name in ("span", "origin"):
            continue

        value = getattr(node, name)

        if isinstance(value, CoreNode):
            children.append((name, value))

        elif name == "binders" and isinstance(value, tuple):
            attributes[name] = list(value)

        elif isinstance(value, tuple):
            for index, item in enumerate(value):
                if isinstance(item, CoreNode):
                    children.append(
                        (f"{name}/{index}", item)
                    )

        elif type(value) in (str, int, bool):
            attributes[name] = value

    child_links = [
        {
            "role": role.replace(
                "/", "[", 1
            ) + ("]" if "/" in role else ""),
            "node_id": f"{node_id}/{role}",
        }
        for role, _ in children
    ]

    record = {
        "node_id": node_id,
        "kind": type(node).__name__,
        "origin": node.origin.value,
        "span": _project_source_span(node.span),
        "attributes": attributes,
        "children": child_links,
    }

    return record, tuple(children)

def project_source_and_core(
    source: str,
    program: CoreProgram,
) -> dict[str, object]:
    """Project source text and the validated Core tree.

    Node identifiers describe structural positions rather than
    Python object identities or simulated heap ObjectIds.
    """
    if not isinstance(source, str):
        raise TypeError("Source must be a string")

    if not isinstance(program, CoreProgram):
        raise TypeError("Expected a CoreProgram")

    root_id = "core"
    pending: list[tuple[str, CoreNode]] = [
        (root_id, program)
    ]
    records: list[dict[str, object]] = []

    # Iterative traversal avoids recursion over deep Core trees.
    while pending:
        node_id, node = pending.pop()

        record, children = _describe_node(
            node,
            node_id,
        )
        records.append(record)

        for role, child in reversed(children):
            pending.append(
                (f"{node_id}/{role}", child)
            )

    return {
        "source": source,
        "core": {
            "root_id": root_id,
            "nodes": records,
        },
    }
