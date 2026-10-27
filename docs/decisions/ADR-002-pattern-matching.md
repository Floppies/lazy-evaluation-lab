# ADR-002: Compile Ordered Function Equations to Selective `CoreCase`

- **Status:** Accepted for static Surface-to-Core lowering
- **Recorded:** 2026-10-19 (documents an earlier design decision)
- **Scope:** Surface v0.1 top-level function equations
- **Related:** [Language specification, §7](../specifications/language-specification.md), [Core IR](../core-ir.md), [B02.8 audit](../audits/b02.8-audit.md)

## Context

Surface v0.1 supports **ordered, consecutive top-level equations** for a single function name. All equations in a group have the same arity. Earlier parameters must be variable patterns; only the final parameter may be a variable, `[]`, or `(head:tail)` pattern. The two `Cons` binders must be distinct.

```haskell
length [] = 0
length (x:xs) = 1 + length xs
```

The compiler must preserve *first-match semantics* without introducing additional demand in lazy strategies. In particular, a variable pattern matches without requiring the argument to reach WHNF; testing `Nil` or `Cons` requires examining only the outer constructor, not the fields.

## Decision

Compile a valid group of function equations to **one global `CoreBinding`** with unary lambdas. Generate a `CoreCase` on the **final argument only when constructor inspection is necessary**.

1. If the first equation ends in a variable pattern, directly curry that equation's original parameters and body. No `CoreCase` or generated parameter aliases are required; subsequent equations are unreachable.
2. Otherwise, allocate fresh internal lambda parameters (for example `$arg0`, `$arg1`) using one `FreshNameSupply` for the entire lowering run.
3. Scan source equations in order. Keep the first `Nil` alternative, the first `Cons` alternative, and the first later variable alternative (if any); discard redundant or unreachable equations from **executable Core**.
4. Generate a single `CoreCase` whose scrutinee is the internal variable for the last function argument. Its alternatives use `CoreConAlt("Nil", ...)`, `CoreConAlt("Cons", ...)`, and, if needed, `CoreDefaultAlt`.
5. Introduce equation-specific aliases of preceding variable parameters using `CoreLetRec`; use `CoreConAlt` binders for `Cons` head and tail.
6. For a variable fallback following constructor alternatives, keep its alias bound to the **original internal argument**. The `CoreDefaultAlt` binder is a fresh internal name and is intentionally not substituted into source-variable references.
7. Leave non-exhaustive groups without an invented fallback. Failure to match any alternative is a runtime pattern-match error.

Example:

```haskell
f x [] = x
f y (h:t) = y
```

Conceptual form:

```text
CoreLam($arg0)
  CoreLam($arg1)
    CoreCase(scrutinee=$arg1)
      Nil       -> letrec { x = $arg0 } in x
      Cons(h,t) -> letrec { y = $arg0 } in y
```

This is a **conceptual outline**, not a new executable Core syntax.

## Alternatives considered

1. **Always emit `CoreCase`, even for a leading variable pattern:** Rejected because inspecting the scrutinee could force an argument needlessly under CBN/CBNeed.
2. **Compile each equation to nested repeated cases:** Unnecessary for this restricted pattern grammar, and risks repeated constructor inspections or altered operational metrics.
3. **Use the inspected `CoreDefaultAlt` value as the fallback's source alias:** Rejected at lowering time because it can impose unwanted sharing on a nonmemoizing CBN evaluator.
4. **Emit a synthetic default for missing cases:** Rejected; non-exhaustive matching is represented by absence of a matching alternative and handled by the runtime.

## Consequences

### Guarantees of the static transformation

- The first applicable equation is selected for the supported patterns.
- A leading variable equation is not made strict by an unnecessary `CoreCase`.
- Only the final argument is inspected for constructor selection.
- `Cons` head and tail are *bound* by a constructor alternative, not explicitly forced by the lowering pass.
- Generated names use the Core-only `$` namespace and are deterministic within a lowering run.

### Open questions and downstream obligations

- **B02.9 — Source diagnostics (audit F02):** Discarded equations are absent from executable Core. A Core-only resolver cannot diagnose their unknown source names. The current language specification generally requires rejecting undefined identifiers; whether to perform a complete Surface name-check before pruning, or an equivalent diagnostic pass, must be settled **before implementing the resolver**. This ADR does not decide the pass order.
- **Runtime behavior (audit F03):** Specify evaluation of the case scrutinee to WHNF, constructor-field demand, aliases, CBN nonmemoization, CBNeed sharing/updates, and CBV behavior. Static Core checks are not proofs of dynamic equivalence.
- **Non-list scrutinees:** Define whether constructor alternatives fail to match and whether a following default applies to values of other runtime kinds; do not infer the policy from Core validation alone.
- **Metrics and provenance (audit F07):** Count constructor inspections and administrative aliases in a manner that permits trustworthy cross-strategy comparisons; spans do not uniquely classify all generated work.
- **Feature limits:** Nested patterns, patterns on earlier parameters, guards, and local pattern equations are out of scope for v0.1. Supporting them requires revisiting this algorithm.

## Verification and references

The [B02.8 audit](../audits/b02.8-audit.md) reports exhaustive static checks of 120 short pattern sequences, deep-structure tests, and specific tests of first-match routing, parameter binding, source spans and generated names. Runtime behavior remains unverified.

## Revisit when

Revisit this ADR when expanding the pattern grammar, changing the Core matching contract, or defining runtime semantics that expose an operational mismatch.
