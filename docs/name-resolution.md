
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

## Core Name Checking

`check_core_names(program)` validates lexical references in a
structurally valid CoreProgram.

The checker supports:

- Mutually recursive global bindings.
- Unary lambda parameters.
- Simultaneous recursive CoreLetRec bindings.
- CoreConAlt constructor-field binders.
- CoreDefaultAlt binders.
- Compiler-generated internal identifiers.

Every alternative of a CoreCase introduces an independent scope.
Alternative binders are not visible in the case scrutinee.

Traversal is iterative and does not depend on Python recursion depth.

## Important Pipeline Requirement

Surface name checking must run before desugaring.

The desugaring stage may remove unreachable function equations.
Consequently, Core name checking alone cannot diagnose undefined
references that existed only in discarded Surface equations.

Both checking passes are required for the v0.1 diagnostic policy.

## Current Limitations

The current implementation checks lexical visibility but does not
rewrite variable references or assign unique binding identifiers.

It does not construct runtime environments, perform type checking,
or determine closure captures.

The runtime must implement lexical lookup and shadowing according
to the same scope rules.
