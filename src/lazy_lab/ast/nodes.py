from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceSpan:
    start_line: int
    start_column: int
    end_line: int
    end_column: int


@dataclass(frozen=True, slots=True, kw_only=True)
class Node:
    span: SourceSpan | None = None


class Expr(Node):
    __slots__ = ()


class Pattern(Node):
    __slots__ = ()


class Definition(Node):
    __slots__ = ()


@dataclass(frozen=True, slots=True)
class Program(Node):
    definitions: tuple[Definition, ...]

@dataclass(frozen=True, slots=True)
class IntLiteral(Expr):
    value: int


@dataclass(frozen=True, slots=True)
class BoolLiteral(Expr):
    value: bool


@dataclass(frozen=True, slots=True)
class Var(Expr):
    name: str


@dataclass(frozen=True, slots=True)
class UnaryOp(Expr):
    operator: str
    operand: Expr


@dataclass(frozen=True, slots=True)
class BinaryOp(Expr):
    operator: str
    left: Expr
    right: Expr


@dataclass(frozen=True, slots=True)
class Application(Expr):
    function: Expr
    argument: Expr