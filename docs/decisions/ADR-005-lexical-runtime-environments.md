# ADR-005: Use Lexical Runtime Environments with Name-Based Lookup

- **Status:** Accepted; implemented for the B04 Core CBV subset. Non-strict evaluation and executable constructor matching remain deferred.
- **Recorded:** 2026-10-20
- **Scope:** CBV/CBN/CBNeed evaluators, closures, shadowing, recursive bindings, runtime visualization
- **Related:** [Language specification, §6](../specifications/language-specification.md), [Name resolution](../name-resolution.md), [Core IR](../core-ir.md), [ADR-001 — Recursive local bindings](ADR-001-core-letrec.md), [ADR-004 — Surface name checking](ADR-004-source-name-checking-before-desugaring.md), [B02.8 audit, F03/F07](../audits/b02.8-audit.md)

## Context

B02.9 checks whether each Surface and Core variable reference has a lexically visible binding. It does **not** assign a unique binding ID to every reference or rewrite `CoreVar(name)` into a resolved-reference node.

The evaluator must nevertheless distinguish bindings with identical names in different scopes:

```haskell
x = 10
main = let { x = 20 } in x
```

The reference in the `let` body must select the local `x`, while a function closure must keep the names visible where it was **defined**, not where it is later called. Top-level definitions and `CoreLetRec` groups are mutually recursive; function applications introduce parameter bindings; case alternatives introduce branch-local binders.

We need a binding model suitable for the same Core IR under CBV, CBN, and CBNeed, without requiring a separate static reference-ID pass before building the first runtime.

## Decision

Use **lexically scoped runtime environments with name-based lookup**.

1. An environment associates identifier strings with runtime bindings and has a lexical parent (or an equivalent representation of enclosing scopes).
2. A variable lookup searches the nearest active lexical scope first, then enclosing scopes. The first binding found wins; an inner binding shadows an outer binding of the same name.
3. Function values are closures that retain the lexical environment in which their `CoreLam` was created. Applying a closure extends **that captured environment** with its parameter binding, not the caller's environment.
4. The runtime establishes a mutually recursive global environment for `CoreProgram` and mutually recursive local environments for `CoreLetRec`: all names in the group are allocated or otherwise made addressable before evaluating or demanding their right-hand sides.
5. `CoreConAlt` and `CoreDefaultAlt` introduce bindings visible only while evaluating their selected alternative's body; their names do not leak to other alternatives or the scrutinee.
6. Compiler-generated identifiers (such as `$arg0` and `$match0`) use the **same lexical lookup rules** as source identifiers. Their prefix is not a shortcut for variable resolution.
7. Environment bindings refer to **strategy-specific runtime representations** (values, delayed computations, heap locations, or equivalent). The environment model defines lexical identity and visibility, not evaluation or memoization policy.

A conceptual lookup rule is:

```text
lookup(name, environment):
    if name occurs in the current frame:
        return the current frame's binding
    otherwise:
        continue in the lexical parent environment
    if no binding exists:
        signal an internal unbound-reference error
```

This pseudocode describes lexical selection, not an exact Python API or runtime object layout.

## Alternatives considered

1. **Assign unique binding IDs during static name resolution:** Makes reference identity explicit and may speed lookup, but adds a new IR/analysis contract and is unnecessary to implement lexical scope in the initial evaluator.
2. **Use dynamic scoping (search the caller's environment):** Rejected because it changes the meaning of closures and violates the language's lexical scoping rules.
3. **Use a single global dictionary for all variables:** Rejected because nested shadowing, independent calls, and captured local bindings cannot be represented faithfully.
4. **Substitute expressions for variable occurrences instead of keeping environments:** Rejected as the initial design because capture-avoiding substitution complicates recursive scopes and risks obscuring the demand/sharing behavior we intend to measure.

## Consequences

### Benefits

- Direct implementation of lexical scope and nearest-binding shadowing without changing existing Core nodes.
- Closures retain their definition-site context; returned functions and partial applications remain representable.
- Mutually recursive globals and local bindings share a common conceptual model.
- The interpreter can execute the same Core syntax under CBV, CBN, and CBNeed while varying demand and memoization rules.
- Runtime environments can later be visualized as frames and links to captured bindings or heap objects.

### Obligations and limitations

- **Recursive initialization:** Define safe group construction for each strategy, especially strict CBV recursive values and cycles. Presence of a name does not mean its value has already been computed.
- **CBV:** Specify when argument expressions and constructor fields are evaluated and how parameter bindings store resulting values.
- **CBN:** Preserve nonmemoizing re-evaluation where required; following compiler-generated aliases must not silently introduce CBNeed-like sharing.
- **CBNeed:** Preserve shared thunk/update identity and define blackhole behavior without duplicating evaluation merely because a name is accessed through an alias.
- **Pattern matching:** `CoreCase` must inspect the scrutinee as required, without eagerly forcing `Cons` fields in lazy strategies. Case/default binders obey their alternative-specific scopes.
- **Instrumentation:** Count or classify frames, bindings, closures, indirections, and heap allocations consistently across strategies. Compiler-generated aliases require explicit attribution (audit F03/F07).
- **Visualizer identities:** Name strings are not globally unique identifiers for bindings. A visualization needing stable references should use runtime frame/binding/heap identities or a separate provenance map, rather than treating `name` alone as identity.
- **Representation and performance:** This ADR does **not** fix the exact environment data structure, frame mutability, heap address scheme, lookup complexity, or closure memory layout. Those are runtime specification decisions.

## Verification and references

The existing B02.9 checkers statically validate lexical visibility over Surface and Core, including recursion and shadowing, but **do not implement or test runtime lookup**. B02.8 lowering tests show that `CoreLam`, `CoreLetRec`, `CoreCase`, and compiler-generated aliases retain the necessary binding structure.

The following list records the runtime acceptance scenarios identified
when this ADR was accepted. B04 now tests the supported CBV scenarios;
constructor matching and non-strict evaluation remain future work.
See the [B04 audit](../audits/b04-audit.md) and
[Core evaluation contract](../core-evaluation-contract.md) for current evidence.

Runtime acceptance scenarios include:

- A local binding shadowing a global binding.
- A closure called from a scope with a conflicting name, proving **definition-site** lookup.
- A returned closure retaining a local binding after its defining call returns.
- Mutual recursion and forward references in global and local groups.
- Independent calls to the same closure using different parameter bindings.
- Constructor/default binders isolated to their selected alternatives.
- Unused divergent arguments, repeated demands, and alias forwarding under all three strategies.

Passing static name checks is **not** evidence that these dynamic tests already pass.

## Revisit when

Revisit this ADR if profiling demonstrates that name-based lookup is an unacceptable overhead, if static binding IDs become necessary for visualization or optimization, or if a revised Core representation changes closure/environment semantics. Any alternative must preserve definition-site lexical scoping, recursive groups, strategy-specific demand/sharing, and observable binding identity.
