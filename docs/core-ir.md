# Core IR — Lazy Evaluation Lab

## Overview

Core is the intermediate representation intended to sit between the surface Abstract Syntax Tree (AST) and evaluation. It makes functions, applications, recursive bindings, and constructor inspection explicit.

The current implementation provides immutable nodes and explicit structural validation. Desugaring from the surface AST is future work.

Core does not select an evaluation strategy. The same expression can be used by call-by-value (CBV), call-by-name (CBN), and call-by-need (CBNeed) evaluators.

## Public API

```python
from lazy_lab.core.nodes import (
    CoreInt, CoreBool, CoreVar, CoreLam, CoreApp, CorePrimOp,
    CoreIf, CoreBinding, CoreLetRec, CoreCon, CoreCase,
    CoreConAlt, CoreDefaultAlt, CoreProgram,
)
from lazy_lab.core.validation import (
    CoreValidationError,
    validate_core_program,
    validate_core_expression,
)
```

### Program validation

`validate_core_program(program: CoreProgram) -> None`

Validates global bindings and their expression trees. An empty program is valid, and a `main` binding is not required.

### Expression validation

`validate_core_expression(expression: CoreExpr) -> None`

Validates one standalone Core expression. Validation is separate from node construction; dataclass constructors do not enforce structural invariants.

Both entry points traverse the tree with an explicit stack rather than Python recursion, allowing validation of deeply nested generated expressions.

## Core Nodes

`CoreNode` is the common base class. `CoreExpr` groups expressions, and `CoreAlt` groups case alternatives. Concrete nodes are frozen dataclasses with slots. Every node accepts an optional keyword-only `span`.

| Node | Fields | Responsibility |
| --- | --- | --- |
| `CoreInt` | `value` | Integer literal; requires an actual Python `int`, excluding `bool`. |
| `CoreBool` | `value` | Boolean literal; requires a Python `bool`. |
| `CoreVar` | `name` | Reference to a binding. |
| `CoreLam` | `parameter`, `body` | Function with exactly one parameter. |
| `CoreApp` | `function`, `argument` | Application of exactly one argument. |
| `CorePrimOp` | `operator`, `arguments` | Primitive arithmetic or comparison operation. |
| `CoreIf` | `condition`, `then_branch`, `else_branch` | Conditional expression. |
| `CoreBinding` | `name`, `rhs` | Association between a name and an expression. |
| `CoreLetRec` | `bindings`, `body` | Nonempty group of mutually recursive bindings and its body. |
| `CoreCon` | `constructor`, `fields` | Data constructor application. |
| `CoreCase` | `scrutinee`, `alternatives` | Selection through constructor inspection. |
| `CoreConAlt` | `constructor`, `binders`, `body` | Constructor alternative with names for its fields. |
| `CoreDefaultAlt` | `binder`, `body` | Catch-all alternative binding the scrutinee. |
| `CoreProgram` | `bindings` | Global program definitions. |

Collection fields (`arguments`, `bindings`, `fields`, `alternatives`, and `binders`) must be tuples. Expression fields must contain Core expressions; binding and alternative collections must contain the corresponding node types.

## Names and Arities

Variable names, lambda parameters, binding names, and alternative binders follow this identifier pattern:

```text
(?:[a-z][a-zA-Z0-9_]*|\$[a-z][a-zA-Z0-9_]*)
```

Ordinary names start with an ASCII lowercase letter, followed by ASCII letters, digits, or underscores. Internal compiler names use a `$` prefix, such as `$arg0` or `$match0`. This namespace is unavailable to identifiers written in the surface language and supports introducing fresh names during desugaring.

Empty names and the reserved names `if`, `then`, `else`, `let`, and `in` are invalid. Names must be unique within each global or recursive binding group and within each constructor alternative's binders. Nested bindings may shadow outer names.

### Functions and applications

Multiple parameters are represented by nested unary lambdas. For example, the Core representation of `add x y = x + y` has this right-hand side:

```python
CoreLam(
    "x",
    CoreLam("y", CorePrimOp("+", (CoreVar("x"), CoreVar("y")))),
)
```

Applications associate to the left. The expression `add 2 3` is represented as:

```python
CoreApp(CoreApp(CoreVar("add"), CoreInt(2)), CoreInt(3))
```

### Primitive operations

| Operators | Number of arguments |
| --- | --- |
| `negate` | 1 |
| `+`, `-`, `*`, `==`, `!=`, `<`, `<=`, `>`, `>=` | 2 |

List construction with `:` is represented by `CoreCon`, rather than a primitive operation.

### Constructors and alternatives

| Constructor | Number of fields / alternative binders |
| --- | --- |
| `Nil` | 0 |
| `Cons` | 2 |

Only these constructors are currently supported. For example, `[1]` is represented as:

```python
CoreCon("Cons", (CoreInt(1), CoreCon("Nil", ())))
```

A `CoreCase` requires at least one alternative, forbids repeated constructor alternatives, and permits at most one default alternative. Alternatives retain their order; validation does not require the default to appear last or reject unreachable alternatives.

### Fresh-name generation

Compiler-generated identifiers use the reserved $ namespace. FreshNameSupply provides deterministic, collision-free names within a single lowering run, with independent counters per prefix and support for reserving existing identifiers.

Surface identifiers cannot contain $, preventing generated binders from capturing source-level names. This mechanism does not perform name resolution or alpha-renaming of user-defined bindings. All generated identifiers within a lowering run must share the same name supply.

## Evaluation Semantics

### Recursive bindings

`CoreLetRec` models a recursive group: every binding in the group is in scope in every right-hand side and in the body. This supports self-reference and mutual recursion.

```python
CoreLetRec(
    bindings=(
        CoreBinding("x", CoreVar("y")),
        CoreBinding("y", CoreInt(10)),
    ),
    body=CoreVar("x"),
)
```

The runtime is responsible for constructing the recursive environment. `CoreLetRec` does not allocate thunks automatically; each evaluator determines how bindings are materialized and how demand cycles are handled.

Global bindings: All bindings contained in CoreProgram belong to a single mutually recursive global scope. Their order is preserved for source correspondence and deterministic representation, but does not restrict name visibility. Runtime environment construction and name resolution must support forward references and mutual recursion between global functions.

### Constructor inspection

To distinguish constructors, `CoreCase` requires its scrutinee to reach weak head normal form (WHNF), exposing the outer constructor. This inspection does not itself force the constructor's fields. Under lazy evaluation, a `Cons` can therefore be inspected without evaluating its head or tail.

```python
CoreCase(
    scrutinee=CoreVar("xs"),
    alternatives=(
        CoreConAlt("Nil", (), CoreInt(0)),
        CoreConAlt("Cons", ("head", "tail"), CoreInt(1)),
    ),
)
```

The `Cons` alternative names the two fields without requiring their evaluation. A `CoreDefaultAlt` provides a catch-all alternative and binds the scrutinee as a whole.

Future desugaring should introduce `CoreCase` when selection requires constructor inspection. A variable-only equation does not by itself require a case expression.

## Error Handling

`CoreValidationError`, a subclass of `ValueError`, reports invalid node structure, field types, identifiers, arities, duplicate names, alternatives, or source spans.

The exception exposes a `span` attribute. When a location is available, the message starts with `line:column:`. A node without its own span inherits the nearest available ancestor span for error reporting.

## Source Locations

Source spans use one-based coordinates, an inclusive start, and an exclusive end. Coordinates must be actual positive integers, and the end cannot precede the start.

Spans are optional and excluded from structural equality. Two otherwise identical Core nodes compare equal even when their source locations differ.

## Representation Boundaries

Core, a future STG-like representation, and runtime objects remain separate representations with different responsibilities.

- **Core** represents expressions and bindings independently of an evaluation strategy.
- **STG-like IR** will be a distinct representation with its own execution-oriented structure.
- **Runtime objects** include environments, closures, thunks, heap addresses, stacks, and update state.

There is no `CoreThunk` node. A thunk is an object an evaluator may create to defer evaluation, rather than a syntactic property of a Core expression. For an application such as `f (1 + 2)`, CBV may evaluate the argument before application, CBN may retain the expression without memoizing it, and CBNeed may allocate a thunk and memoize its result. The Core tree is the same.

## Desugaring Implementation

Surface-to-Core desugaring uses an explicit postorder traversal for expression trees. This avoids Python recursion-depth failures when lowering deeply nested Surface AST structures, including long left-associative operator chains.

The transformation preserves source-level expression structure, introduces unary lambdas, normalizes list constructors, and compiles ordered function equations to Core case expressions when constructor inspection is required.

Desugaring does not evaluate expressions, perform name resolution, eliminate unused bindings, or select an evaluation strategy.

## Current Limitations

- Validation does not resolve names or check scopes; `CoreVar("unknown")` is structurally valid.
- Validation does not perform type checking; `CoreApp(CoreInt(1), CoreInt(2))` is structurally valid.
- Validation does not check pattern-match exhaustiveness or reachability.
- Constructors are restricted to `Nil` and `Cons`.
- Surface-to-Core desugaring, fresh-name generation, name resolution, and runtime evaluation are outside the current Core implementation.
