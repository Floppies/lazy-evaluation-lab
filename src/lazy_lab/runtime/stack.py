
"""Explicit continuation frames and stack storage."""

from __future__ import annotations

from dataclasses import dataclass, field

from lazy_lab.core.nodes import CoreAlt, CoreApp, CoreCase, CoreExpr, CoreIf, CorePrimOp

from .environment import Environment
from .references import RuntimeRef, HeapReference
from .control import InitializeLocalBindings


class StackFrame:
    """Base class for abstract machine continuation frames."""

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class ApplyFunctionFrame(StackFrame):
    argument: CoreExpr
    environment: Environment
    awaiting_whnf: bool = False
    application: CoreApp | None = None


@dataclass(frozen=True, slots=True)
class ApplyArgumentFrame(StackFrame):
    function: RuntimeRef
    return_environment: Environment | None = None
    awaiting_whnf: bool = False
    application: CoreApp | None = None


@dataclass(frozen=True, slots=True)
class IfFrame(StackFrame):
    then_branch: CoreExpr
    else_branch: CoreExpr
    environment: Environment
    awaiting_whnf: bool = False
    conditional: CoreIf | None = field(
        default=None,
        compare=False,
    )


@dataclass(frozen=True, slots=True)
class GlobalDemandFrame(StackFrame):
    """Resume the caller after evaluating a pending global RHS."""

    return_environment: Environment
    pending_reference: HeapReference
    awaiting_whnf: bool = False


@dataclass(frozen=True, slots=True)
class UpdateFrame(StackFrame):
    """Track evaluation of a Call-by-Need thunk.

    thunk_reference identifies the stable one-slot anchor
    that must eventually receive the WHNF update.

    return_environment is the caller's lexical environment,
    restored after the update continuation completes.

    awaiting_whnf distinguishes the initial RHS return
    from a return following explicit WHNF demand.
    """

    thunk_reference: HeapReference
    return_environment: Environment
    awaiting_whnf: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.thunk_reference, HeapReference):
            raise TypeError(
                "UpdateFrame requires a thunk HeapReference"
            )

        if not isinstance(self.return_environment, Environment):
            raise TypeError(
                "UpdateFrame requires a return Environment"
            )

        if type(self.awaiting_whnf) is not bool:
            raise TypeError(
                "awaiting_whnf must be a boolean"
            )


@dataclass(frozen=True, slots=True)
class RestoreEnvironmentFrame(StackFrame):
    environment: Environment


@dataclass(frozen=True, slots=True)
class PrimitiveOperandsFrame(StackFrame):
    """Track left-to-right strict primitive operand evaluation."""

    operator: str
    remaining_arguments: tuple[CoreExpr, ...]
    evaluated_arguments: tuple[RuntimeRef, ...]
    environment: Environment
    awaiting_whnf: bool = False

    primitive: CorePrimOp | None = field(
        default=None,
        compare=False,
    )
    

@dataclass(frozen=True, slots=True)
class LocalValueInitializationFrame(StackFrame):
    """Resume local CBV initialization after demanding a RHS."""

    binding_reference: HeapReference
    continuation: InitializeLocalBindings
    environment: Environment
    awaiting_whnf: bool = False


@dataclass(frozen=True, slots=True)
class SeqFirstArgumentFrame(StackFrame):
    """Resume CBNeed seq after its first argument reaches WHNF."""

    first_argument_reference: RuntimeRef
    second_expression: CoreExpr
    return_environment: Environment
    application: CoreApp | None = None


@dataclass(frozen=True, slots=True)
class ConstructorFieldsFrame(StackFrame):
    """Track left-to-right strict constructor field evaluation."""

    constructor: str
    remaining_fields: tuple[CoreExpr, ...]
    evaluated_fields: tuple[RuntimeRef, ...]
    environment: Environment
    awaiting_whnf: bool = False


@dataclass(frozen=True, slots=True)
class CoreCaseFrame(StackFrame):
    """Track Core case evaluation and ordered alternatives."""

    alternatives: tuple[CoreAlt, ...]
    environment: Environment
    awaiting_whnf: bool = False
    scrutinee_reference: RuntimeRef | None = None
    selected_alternative: CoreAlt | None = None
    case_expression: CoreCase | None = field(
        default=None,
        compare=False,
    )


@dataclass(frozen=True, slots=True)
class MaterializationDemandFrame(StackFrame):
    """Resume result materialization after a field reaches WHNF."""

    root_reference: RuntimeRef
    return_environment: Environment


class EmptyStackError(LookupError):
    """Raised when accessing an empty stack."""


class Stack:
    def __init__(self) -> None:
        self._frames: list[StackFrame] = []

    @property
    def depth(self) -> int:
        return len(self._frames)

    @property
    def frames(self) -> tuple[StackFrame, ...]:
        return tuple(self._frames)

    def push(self, frame: StackFrame) -> None:
        if not isinstance(frame, StackFrame):
            raise TypeError("Expected a StackFrame")

        self._frames.append(frame)

    def pop(self) -> StackFrame:
        if not self._frames:
            raise EmptyStackError("Cannot pop an empty stack")

        return self._frames.pop()

    def peek(self) -> StackFrame:
        if not self._frames:
            raise EmptyStackError("Cannot peek an empty stack")

        return self._frames[-1]

    def clone(self) -> Stack:
        result = Stack()
        result._frames = self._frames.copy()
        return result
