from __future__ import annotations

from lazy_lab.ast.validation import validate_program
from lazy_lab.core import nodes as core
from lazy_lab.core.desugar import lower_program
from lazy_lab.core.validation import validate_core_program
from lazy_lab.frontend.parser import parse_program
from lazy_lab.semantics.name_resolution import (
    check_surface_names,
    check_core_names,
)


def compile_source(source: str) -> core.CoreProgram:
    """Compile source code into validated, name-checked Core IR."""
    surface_program = parse_program(source)

    validate_program(surface_program)
    check_surface_names(surface_program)

    core_program = lower_program(surface_program)

    validate_core_program(core_program)
    check_core_names(core_program)

    return core_program