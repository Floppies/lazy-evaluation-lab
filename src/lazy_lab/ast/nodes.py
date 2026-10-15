from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """One-based source range with an inclusive start and exclusive end.

    Structural validation rejects empty ranges on concrete syntax nodes;
    an empty Program may have an empty range.
    """

    start_line: int
    start_column: int
    end_line: int
    end_column: int


@dataclass(frozen=True, slots=True, kw_only=True)
class Node:
    """AST data with optional location metadata excluded from equality and hashing.

    Constructors do not validate arguments. Structural validation enforces
    field types and tuple containers before later frontend stages use them.
    """

    span: SourceSpan | None = field(default=None, compare=False)


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


@dataclass(frozen=True, slots=True)
class LambdaExpr(Expr):
    parameters: tuple[str, ...]
    body: Expr


@dataclass(frozen=True, slots=True)
class IfExpr(Expr):
    condition: Expr
    then_branch: Expr
    else_branch: Expr


@dataclass(frozen=True, slots=True)
class LocalBinding(Node):
    name: str
    parameters: tuple[str, ...]
    rhs: Expr


@dataclass(frozen=True, slots=True)
class LetExpr(Expr):
    bindings: tuple[LocalBinding, ...]
    body: Expr


@dataclass(frozen=True, slots=True)
class ListLiteral(Expr):
    elements: tuple[Expr, ...]


@dataclass(frozen=True, slots=True)
class VarPattern(Pattern):
    name: str


@dataclass(frozen=True, slots=True)
class NilPattern(Pattern):
    pass


@dataclass(frozen=True, slots=True)
class ConsPattern(Pattern):
    head: VarPattern
    tail: VarPattern


@dataclass(frozen=True, slots=True)
class ValueDefinition(Definition):
    name: str
    rhs: Expr


@dataclass(frozen=True, slots=True)
class FunctionEquation(Definition):
    name: str
    parameters: tuple[Pattern, ...]
    rhs: Expr
