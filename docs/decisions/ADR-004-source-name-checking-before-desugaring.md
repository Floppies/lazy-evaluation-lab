# ADR-004: Check All Surface Names Before Desugaring

- **Status:** Accepted; implemented in B02.9
- **Recorded:** 2026-10-20
- **Scope:** Surface v0.1 name diagnostics, compilation pipeline, Core name checking
- **Related:** [Language specification, §9](../specifications/language-specification.md), [Name resolution](../name-resolution.md), [Core IR](../core-ir.md), [ADR-002 — Ordered pattern matching](ADR-002-pattern-matching.md), [B02.8 audit, F02](../audits/b02.8-audit.md)

## Context

Surface v0.1 allows ordered top-level function equations. Desugaring preserves first-match behavior by removing equations that cannot be selected. This is sound for the executable structure, but can remove references before a Core-only name checker sees them:

```haskell
f x = 10
f [] = unknown
```

The second equation is unreachable, yet `unknown` is still an undefined source identifier. The language specification requires undefined names to be rejected; it does not exempt unreachable equations or unselected conditional branches.

The B02.8 audit identified this mismatch as **F02**. A name checker operating only on the lowered Core program cannot diagnose every reference in the original source.

## Decision

**Validate lexical name visibility over the entire Surface program before desugaring, and check names again in the resulting Core program.**

The public source compilation pipeline, `compile_source(source: str) -> CoreProgram`, follows this order:

1. Parse the source into a Surface AST.
2. Validate Surface AST structure.
3. Run `check_surface_names(program)` on **all** Surface definitions and expressions.
4. Lower the Surface AST to Core IR.
5. Validate Core structure.
6. Run `check_core_names(program)` on all retained and compiler-generated Core references.

Both name-checking passes require structurally validated inputs. They return `None` on success and raise `NameResolutionError` for undefined references, using source locations when available.

**Static diagnostic policy:** Every variable reference in the original Surface program must resolve to a lexically visible name, including references in unreachable equations, unused recursive bindings, and unselected `if` branches. Name checking does not execute expressions and does not reject recursion just because it is cyclic.

Surface checking and Core checking enforce compatible lexical scope rules, but have distinct coverage:

- **Surface:** Source-level global definitions, equation-specific pattern parameters, lambdas, recursive `let` groups, and shadowing; checks equations that lowering may discard.
- **Core:** Global bindings, unary lambdas, `CoreLetRec`, `CoreConAlt`, `CoreDefaultAlt`, and internal `$` identifiers; checks the actual representation passed to the runtime.

`compile_source()` is the recommended public entry point for source programs. Lower-level validators, name checkers, and `lower_program()` remain usable independently by tools and tests, and do not by themselves enforce the whole pipeline.

## Alternatives considered

1. **Check names only after lowering:** Rejected because unreachable source equations disappear before diagnostics, violating the source-level unknown-name policy.
2. **Retain discarded equations or their references in Core:** Avoids a separate Surface pass but complicates executable Core with diagnostic-only source information.
3. **Resolve names during lowering:** Could inspect all original equations, but couples lexical diagnostics to pattern compilation and makes both passes harder to audit separately.
4. **Allow undefined identifiers in unreachable source:** Rejected for v0.1 because it weakens the existing static diagnostic rule and makes diagnostics depend on compiler pruning.

## Consequences

### Benefits

- Closes the B02.8 audit's F02 diagnostic gap at the public source pipeline boundary.
- Keeps source diagnostics independent of optimizations that remove unreachable equations.
- Verifies compiler-generated Core names after lowering without requiring a binding-ID rewrite.
- Preserves separation between structural validation, lexical checking, desugaring, and runtime evaluation.

### Obligations and limitations

- **Pipeline order is contractual.** New public source-compilation paths must call both name checkers in the specified order or delegate to `compile_source()`.
- **No reference-to-binding map:** The current passes check visibility; they do not assign unique binding IDs, construct closures, or produce resolved-variable Core nodes.
- **Runtime responsibility:** The evaluator must still implement correct lexical binding identity and shadowing when looking up values (see ADR-005).
- **No static type or termination analysis:** A name may resolve even when its value diverges, has the wrong runtime type, or would trigger a blackhole.
- **Source locations:** Diagnostics use the offending identifier's `SourceSpan` where available, with inherited locations as supported by each checker.

## Verification and references

B02.9 introduced separate Surface and Core name-checking tests and a public `compile_source()` pipeline. Regression cases include an undefined name in an unreachable catch-all equation and in a duplicate-constructor equation, plus forward references, mutual recursion, shadowing, and deep input traversal.

These tests establish **static visibility and pass-order behavior**, not runtime lexical lookup or dynamic equivalence. The [B02.8 audit](../audits/b02.8-audit.md) remains a historical snapshot reporting F02 as unresolved *at that time*; this ADR records its later resolution.

## Revisit when

Revisit this ADR if the language changes its static diagnostic policy, adds a pre-lowering optimizer that drops source expressions, introduces a different name-binding representation, or adopts a unified semantic-analysis pass. Any replacement must still account for references in the original source, or explicitly revise the specification and tests.
