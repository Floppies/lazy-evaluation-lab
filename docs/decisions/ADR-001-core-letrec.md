# ADR-001: Represent Local Recursive Bindings with `CoreLetRec`

- **Status:** Accepted
- **Recorded:** 2026-10-19 (documents an earlier design decision)
- **Scope:** Surface v0.1, Surface-to-Core lowering, future evaluators
- **Related:** [Language specification, §6](../specifications/language-specification.md), [Core IR](../core-ir.md), [B02.8 audit](../audits/b02.8-audit.md), [ADR-007 — Thunk Identity and Payload](ADR-007-separate-thunk-identity-from-evaluation-payload.md)

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

### Call-by-Need Runtime Integration (B05)

Under Call-by-Need, deferred function arguments, non-lambda
global bindings in CoreProgram, and non-lambda local bindings
in CoreLetRec use the same thunk evaluation and memoization
protocol.

Each deferred computation has a stable one-slot identity
anchor and a separately allocated ThunkPayload, as defined
in ADR-007.

Demand follows the common lifecycle:

PendingThunk -> EvaluatingThunk -> Indirection(WHNF)

The evaluator uses the same Force transitions and UpdateFrame
continuations for all three binding origins. This guarantees
consistent sharing, WHNF demand, memoization, and blackhole
detection without implementing separate forcing algorithms
for global, local, and argument thunks.

Global and local recursive bindings reserve their addresses
before installing their right-hand sides. Function arguments
receive fresh thunk anchors when applied under CBNeed.

Top-level lambdas remain directly installed closures, while
local lambda bindings may retain an Indirection to a separately
allocated closure. These function representations do not
require deferred thunk payloads.

This integration does not change the strategy-independent
CoreLetRec representation or the lexical scoping rules.
CBV retains strict local initialization, and CBN remains
a separate nonmemoizing strategy.

The concrete thunk representation and its memory-accounting
consequences are documented in ADR-007.

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

Revisit this ADR if the language gains nonrecursive `let`,
local pattern equations, or a different scoping model;
if experimental evidence shows that CoreLetRec prevents
accurate strategy-specific instrumentation; or if the
shared CBNeed thunk protocol introduces semantic
inconsistencies or unacceptable representation costs
between global bindings, local bindings, and function
arguments.

Changes to the thunk identity, payload layout, or update
protocol must also reconsider ADR-007.

Any revision must preserve the intended recursive scope,
lexical binding identity, and strategy-specific evaluation
semantics, or explicitly document changes to those contracts.
Corresponding language specifications, runtime contracts,
and tests must be updated.
