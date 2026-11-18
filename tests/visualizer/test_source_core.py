
"""Tests for static Source/Core projection."""

import json

import pytest

from lazy_lab.core.nodes import (
    CoreBinding,
    CoreInt,
    CoreProgram,
)
from lazy_lab.pipeline import compile_source
from lazy_lab.source import OriginKind
from lazy_lab.visualizer.source_core import (
    project_source_and_core,
)


def project(source):
    return project_source_and_core(
        source,
        compile_source(source),
    )


def test_simple_program_has_structural_node_ids():
    result = project("main = 1 + 2")

    nodes = {
        node["node_id"]: node
        for node in result["core"]["nodes"]
    }

    assert result["source"] == "main = 1 + 2"
    assert result["core"]["root_id"] == "core"

    assert nodes["core"]["kind"] == "CoreProgram"

    binding = nodes["core/bindings/0"]

    assert binding["kind"] == "CoreBinding"
    assert binding["attributes"]["name"] == "main"

    operation = nodes["core/bindings/0/rhs"]

    assert operation["kind"] == "CorePrimOp"
    assert operation["attributes"]["operator"] == "+"

    assert operation["children"] == [
        {
            "role": "arguments[0]",
            "node_id": "core/bindings/0/rhs/arguments/0",
        },
        {
            "role": "arguments[1]",
            "node_id": "core/bindings/0/rhs/arguments/1",
        },
    ]

    left = nodes["core/bindings/0/rhs/arguments/0"]
    right = nodes["core/bindings/0/rhs/arguments/1"]

    assert left["attributes"]["value"] == 1
    assert right["attributes"]["value"] == 2

    json.dumps(result, allow_nan=False)


def test_node_ids_are_unique_and_deterministic():
    source = "main = let { x = 1 + 2 } in x + x"
    program = compile_source(source)

    first = project_source_and_core(source, program)
    second = project_source_and_core(source, program)

    assert first == second

    nodes = first["core"]["nodes"]
    ids = [node["node_id"] for node in nodes]

    assert len(ids) == len(set(ids))

    known_ids = set(ids)

    for node in nodes:
        for child in node["children"]:
            assert child["node_id"] in known_ids


def test_generated_list_constructors_keep_provenance():
    result = project("main = [1, 2]")

    nodes = result["core"]["nodes"]

    generated = [
        node for node in nodes
        if node["origin"] == "GENERATED"
    ]

    assert generated

    constructors = [
        node for node in generated
        if node["kind"] == "CoreCon"
    ]

    assert any(
        node["attributes"]["constructor"] == "Cons"
        for node in constructors
    )
    assert any(
        node["attributes"]["constructor"] == "Nil"
        for node in constructors
    )

    assert len({
        node["node_id"] for node in generated
    }) == len(generated)


def test_source_spans_preserve_existing_coordinates():
    result = project("main = 1 + 2")

    operation = next(
        node
        for node in result["core"]["nodes"]
        if node["kind"] == "CorePrimOp"
    )

    assert operation["origin"] == "SOURCE"

    span = operation["span"]
    assert span is not None

    assert span["start_line"] == 1
    assert span["end_line"] == 1
    assert span["start_column"] < span["end_column"]


def test_missing_span_is_not_invented():
    program = CoreProgram(
        bindings=(
            CoreBinding(
                name="main",
                rhs=CoreInt(7),
            ),
        ),
        origin=OriginKind.UNKNOWN,
    )

    result = project_source_and_core(
        "main = 7",
        program,
    )

    assert all(
        node["span"] is None
        for node in result["core"]["nodes"]
    )


def test_source_and_core_projection_is_passive():
    source = "main = [1, 2]"
    program = compile_source(source)

    first_binding = program.bindings[0]
    original_rhs = first_binding.rhs

    first = project_source_and_core(source, program)
    second = project_source_and_core(source, program)

    assert first == second
    assert program.bindings[0] is first_binding
    assert first_binding.rhs is original_rhs


def test_invalid_arguments_are_rejected():
    program = compile_source("main = 42")

    with pytest.raises(TypeError, match="Source"):
        project_source_and_core(None, program)

    with pytest.raises(TypeError, match="CoreProgram"):
        project_source_and_core("main = 42", None)
