
# Name Resolution

## Purpose

Name resolution checks that identifier references correspond to
lexically visible bindings.

It does not evaluate expressions, perform type checking, or
construct runtime environments.

## Diagnostic policy

Every Surface identifier reference must resolve to a visible
binding, including references in unreachable function equations
and conditional branches.

Unknown identifiers are static errors.

## Lexical scopes

- Top-level definitions belong to one mutually recursive scope.
- Lambda parameters are visible inside their bodies.
- Local `let` bindings are mutually recursive.
- Function equations have independent parameter scopes.
- Constructor-pattern binders are visible in their equation RHS.
- Inner bindings shadow outer bindings.
- Recursive references are permitted and are not evaluated
  during name resolution.

## Pipeline

1. Parse source code.
2. Validate the Surface AST.
3. Check names in the complete Surface AST.
4. Lower Surface to Core.
5. Validate the Core IR.
6. Check Core names, including compiler-generated binders.

## Out of scope

- Type checking.
- Runtime error detection.
- Blackhole detection.
- Free-variable capture and closure allocation.
- Optimization.
- Evaluation strategy selection.

## Status

Surface name checking is pending implementation in B02.9.2.
Core name checking is planned for B02.9.3.
