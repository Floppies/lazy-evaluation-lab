# Name Resolution

## Purpose and Public API

Name checking verifies that every identifier reference has a lexically visible binding. It does not evaluate expressions or rewrite the AST.

- `check_surface_names(program: surface.Program) -> None`
- `check_core_names(program: core.CoreProgram) -> None`

Both functions require structurally validated inputs. Successful checking returns `None`; an undefined reference raises `NameResolutionError`, with a `SourceSpan` when location information is available.

These passes check **visibility**, not the identity of the binding selected by a reference. Lexical lookup will also be required in the runtime.

## Shared Lexical Scope Rules

- **Global definitions:** All top-level bindings share one mutually recursive scope. Forward references and mutual recursion are allowed regardless of declaration order.
- **Lambdas:** Parameters are visible only inside their bodies.
- **Recursive local bindings:** Names in a `let` / `CoreLetRec` group are visible in every binding RHS and in the group body. Local function parameters are visible only in their own RHS.
- **Shadowing:** Inner bindings may shadow outer ones; the innermost visible binding takes precedence. Duplicate names within a single binding group are handled by structural validation.
- **Recursion:** Self-reference is legal at the name-checking stage. Termination and cyclic evaluation are runtime concerns.
- i**Predefined identifiers:** The name `seq` is available in an outer lexical scope. Global and local definitions may shadow it. Both Surface and Core name checkers recognize the same predefined identifiers without inserting synthetic bindings into `CoreProgram`. Runtime binding selection remains the evaluator's responsibility.

## Surface AST Name Checking

`check_surface_names()` checks the complete, validated Surface program **before desugaring**.

Each `FunctionEquation` has an independent parameter scope. `VarPattern` binds one name, `ConsPattern` binds its head and tail names, and `NilPattern` binds none. The equation's binders are visible only in its RHS.

All references are checked, including those in unselected conditional branches, unused local definitions, and unreachable function equations. For example:

```haskell
f x = 10
f [] = unknown
```

This program raises `NameResolutionError` for `unknown`, even though the second equation would be removed by pattern compilation. This policy addresses audit finding **F02**.

## Core IR Name Checking

`check_core_names()` checks the validated `CoreProgram` produced by desugaring, including compiler-generated identifiers such as `$arg0` and `$match0`.

Core-specific binders are introduced by:

- `CoreLam`: its parameter.
- `CoreLetRec`: all bindings in its mutually recursive group.
- `CoreConAlt`: its constructor-field binders.
- `CoreDefaultAlt`: its default binder.

Each `CoreCase` alternative has an independent scope. Alternative binders are **not** visible in the scrutinee or in other alternatives.

The Core pass verifies references retained or introduced by lowering; it cannot inspect Surface equations that lowering discarded.

## Pipeline and Diagnostics

The recommended entry point for source programs is `compile_source(source: str) -> core.CoreProgram`, which runs:

1. Parse source code into Surface AST.
2. Validate Surface structure.
3. Check all Surface names.
4. Lower Surface AST to Core IR.
5. Validate Core structure.
6. Check Core names.

**Surface name checking must precede desugaring.** Both passes are required for the v0.1 policy on undefined identifiers.

Name errors are static, regardless of whether an expression would execute. Diagnostics use the offending reference's source location when available, falling back to an enclosing location where supported.

## Implementation

Both checkers use an iterative depth-first traversal with explicit scope-entry and scope-exit tasks. Active-name counts support shadowing without copying the environment for each nested scope. Global bindings are registered before visiting their RHSs; recursive local groups are registered before visiting any member RHS.

The traversal does not depend on Python's recursion depth and does not construct runtime environments.

## Limitations

Name checking does **not** assign binding IDs, produce reference-to-binding maps, perform type checking or exhaustiveness analysis, detect blackholes or nontermination, determine closure captures, or select an evaluation strategy.

The runtime must implement lexical environments and shadowing consistently with these rules. Operational behavior under CBV, CBN, and CBNeed remains a separate concern.
