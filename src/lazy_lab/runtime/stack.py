
"""Explicit continuation frames and stack storage."""

from __future__ import annotations

from dataclasses import dataclass

from lazy_lab.core.nodes import CoreExpr

from .environment import Environment
from .references import RuntimeRef, HeapReference


class StackFrame:
    """Base class for abstract machine continuation frames."""

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class ApplyFunctionFrame(StackFrame):
    argument: CoreExpr
    environment: Environment
    awaiting_whnf: bool = False


@dataclass(frozen=True, slots=True)
class ApplyArgumentFrame(StackFrame):
    function: RuntimeRef
    return_environment: Environment | None = None
    awaiting_whnf: bool = False


@dataclass(frozen=True, slots=True)
class IfFrame(StackFrame):
    then_branch: CoreExpr
    else_branch: CoreExpr
    environment: Environment


@dataclass(frozen=True, slots=True)
class GlobalDemandFrame(StackFrame):
    """Resume the caller after evaluating a pending global RHS."""

    return_environment: Environment
    pending_reference: HeapReference
    awaiting_whnf: bool = False


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
