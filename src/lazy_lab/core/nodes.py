from __future__ import annotations

from dataclasses import dataclass, field

from lazy_lab.source import SourceSpan


@dataclass(frozen=True, slots=True, kw_only=True)
class CoreNode:
    span: SourceSpan | None = field(
        default=None,
        compare=False,
    )


class CoreExpr(CoreNode):
    __slots__ = ()


@dataclass(frozen=True, slots=True)
class CoreInt(CoreExpr):
    value: int


@dataclass(frozen=True, slots=True)
class CoreBool(CoreExpr):
    value: bool


@dataclass(frozen=True, slots=True)
class CoreVar(CoreExpr):
    name: str


@dataclass(frozen=True, slots=True)
class CoreLam(CoreExpr):
    parameter: str
    body: CoreExpr


@dataclass(frozen=True, slots=True)
class CoreApp(CoreExpr):
    function: CoreExpr
    argument: CoreExpr


@dataclass(frozen=True, slots=True)
class CorePrimOp(CoreExpr):
    operator: str
    arguments: tuple[CoreExpr, ...]


@dataclass(frozen=True, slots=True)
class CoreIf(CoreExpr):
    condition: CoreExpr
    then_branch: CoreExpr
    else_branch: CoreExpr

@dataclass(frozen=True, slots=True)
class CoreBinding(CoreNode):
    name: str
    rhs: CoreExpr


@dataclass(frozen=True, slots=True)
class CoreLetRec(CoreExpr):
    bindings: tuple[CoreBinding, ...]
    body: CoreExpr

@dataclass(frozen=True, slots=True)
class CoreCon(CoreExpr):
    constructor: str
    fields: tuple[CoreExpr, ...]

class CoreAlt(CoreNode):
    __slots__ = ()


@dataclass(frozen=True, slots=True)
class CoreConAlt(CoreAlt):
    constructor: str
    binders: tuple[str, ...]
    body: CoreExpr


@dataclass(frozen=True, slots=True)
class CoreDefaultAlt(CoreAlt):
    binder: str
    body: CoreExpr


@dataclass(frozen=True, slots=True)
class CoreCase(CoreExpr):
    scrutinee: CoreExpr
    alternatives: tuple[CoreAlt, ...]

@dataclass(frozen=True, slots=True)
class CoreProgram(CoreNode):
    bindings: tuple[CoreBinding, ...]