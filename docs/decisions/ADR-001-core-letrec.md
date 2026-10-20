# ADR-001: Represent Local Recursive Bindings with `CoreLetRec`

- **Status:** Accepted
- **Recorded:** 2026-10-19 (documents an earlier design decision)
- **Scope:** Surface v0.1, Surface-to-Core lowering, future evaluators
- **Related:** [Language specification, §6](../language-specification.md), [Core IR](../core-ir.md), [B02.8 audit](../audits/b02.8-audit.md)

## Context

The mini-language allows mutually recursive local definitions:

```haskell
let { x = y; y = 10 } in x
```

Every name in a `let` group is visible in every right-hand side and in the group body, including self-references. Local functions may have multiple ordinary identifier parameters, but local pattern-matching equations are not supported in v0.1. Lexical shadowing of enclosing names is allowed; duplicate definitions within the same group are not.

We need a Core representation that retains these scoping rules without committing to a particular evaluation strategy. The project has a single Core IR intended for CBV, CBN, and CBNeed.

## Decision

Lower each Surface `LetExpr` to **one `CoreLetRec` node** whose bindings are `CoreBinding` entries and whose body is the lowered `let` body.

- All bindings in the group have **simultaneous, mutually recursive scope**.
- Local function parameters are converted to nested unary `CoreLam` nodes in parameter order.
- The lowering pass preserves unused and cyclic bindings; it does not execute, simplify, or reject them for being recursive.
- Top-level definitions are represented as bindings in a `CoreProgram`, whose bindings also form one mutually recursive global scope. A top-level `CoreLetRec` wrapper is not introduced.
- Compiler-generated parameter aliases may also use `CoreLetRec`; their operational handling and instrumentation costs must be specified by the evaluator.

Example:

```haskell
let { x = y; y = 10 } in x
```

Conceptual Core:

```python
CoreLetRec(
    bindings=(
        CoreBinding("x", CoreVar("y")),
        CoreBinding("y", CoreInt(10)),
    ),
    body=CoreVar("x"),
)
```

## Alternatives considered

1. **Sequential nonrecursive bindings:** Simpler environments, but incorrectly make binding order control visibility and disallow valid mutual recursion.
2. **Separate recursive and nonrecursive Core binding forms:** Potentially useful for optimization, but unnecessary for the initial language and would expand Core semantics.
3. **Encode recursion with fixed-point combinators:** Introduces transformations and runtime concerns that obscure the source's explicit recursive scopes.

## Consequences

### Benefits

- Direct correspondence with Surface `let` scoping.
- Recursion and shadowing remain explicit in Core.
- One source-independent Core representation can be interpreted by all three evaluation strategies.
- The desugaring pass stays structural and does not allocate runtime objects.

### Obligations and limitations

- **Name resolution:** `CoreLetRec` bindings must be in scope for all right-hand sides and the body; forward references and self-reference are legal.
- **Runtime:** Each strategy must define recursive environment initialization, demand, evaluation/update behavior, and handling of cycles or blackholes. `CoreLetRec` itself does not allocate thunks.
- **Instrumentation:** Distinguish source-authored bindings from compiler-generated aliases when attributing memory allocations and semantic work. Source spans alone are insufficient to identify all administrative work (audit F03/F07).
- **CBV:** The behavior of recursive value initialization must be defined explicitly; do not assume cyclic values are usable under strict evaluation.

## Verification and references

B02.8 tests establish structural lowering of mutually recursive local bindings and global forward references. They do **not** prove dynamic equivalence across strategies. See the [B02.8 audit](../audits/b02.8-audit.md), especially F03 and F07.

## Revisit when

Revisit this ADR if the language gains nonrecursive `let`, local pattern equations, a different scoping model, or experimental evidence shows that the representation prevents accurate strategy-specific instrumentation. Changes require corresponding specification and test updates.
