# ADR-007: Separate Thunk Identity from Evaluation Payload

- **Status:** Accepted
- **Recorded:** 2026-11-06 (documents the B05 Call-by-Need design decision)
- **Scope:** Core CBNeed runtime, heap layout, thunk updates, sharing, snapshots, and memory accounting
- **Related:** [ADR-001 — CoreLetRec](ADR-001-core-letrec.md), [ADR-005 — Lexical Runtime Environments](ADR-005-lexical-runtime-environments.md), [ADR-006 — Stable Recursive Binding Cells](ADR-006-stable-recursive-binding-cells.md), [Core Evaluation Contract, §§7.10–7.11](../core-evaluation-contract.md)

## Context

Call-by-Need must preserve the identity of a deferred computation across its first demand, evaluation, and subsequent uses. Several references may share the same computation, including function arguments, global bindings, and local recursive bindings. Updating its result must not invalidate those references or mutate previous execution snapshots.

The simulated heap assigns stable object addresses with fixed allocation capacities. A deferred expression may retain a variable number of free local references, so the amount of storage needed for its evaluation payload cannot be assumed to fit in a one-slot binding cell. Recursive bindings may also need an address before their right-hand sides are initialized, as established by ADR-006.

We need a common representation that supports memoization, lexical capture, recursive references, deterministic snapshots, and explicit allocation costs without resizing heap cells.

## Decision

Represent each Call-by-Need deferred computation using **a stable one-slot identity anchor and a separately allocated, immutable evaluation payload**.

1. **Anchor:** A `HeapReference` identifies a one-slot cell containing `PendingThunk(payload_reference)` before demand, `EvaluatingThunk(payload_reference)` during evaluation, or `Indirection(whnf_reference)` after a successful update. Its `ObjectId` and allocated capacity never change.
2. **Payload:** A `ThunkPayload` stores the deferred Core expression and a standalone environment containing **only the required free local references**. Global and predefined references are resolved through the shared global environment; the payload does not capture them as locals.
3. **Allocation:** A fresh deferred computation allocates one payload and one anchor. When a global or recursive local binding already owns a one-slot `Reserved` anchor, the runtime initializes that anchor instead of allocating another one. The payload remains separate in either case.
4. **Demand and update:** The first force changes the anchor to `EvaluatingThunk` and installs an `UpdateFrame`. After the result reaches WHNF, the runtime replaces the original anchor with `Indirection(whnf_reference)`. Subsequent demands follow the indirection rather than reevaluating the RHS.
5. **Snapshots:** Lifecycle transitions replace heap-cell contents only in an isolated successor state. Payloads and unchanged immutable heap objects may be shared safely by historical snapshots.

This decision concerns the representation of **deferred CBNeed computations**. It does not require top-level or local lambda bindings, which may be installed directly as closures or through an indirection to a closure, to allocate a thunk payload. It does not introduce sharing into CBV or CBN.

The abstract allocation cost of a fresh thunk is **2 + N slots**, where `N` is the number of captured free local references: one anchor slot and `1 + N` payload slots. For a previously reserved anchor, its one slot has already been accounted for when the binding group was reserved.

## Rationale

Separating identity from payload permits references to remain stable while the deferred computation changes lifecycle state. It also avoids predicting or resizing the storage required for captured references. The model exposes both the administrative anchor cost and the payload cost for later instrumentation, while remaining compatible with recursive scope reservation and snapshot isolation.

This extends ADR-006 rather than replacing it: ADR-006 establishes stable binding cells for local recursion; this ADR specifies the representation and lifecycle of deferred Call-by-Need computations more generally.

## Alternatives Considered

1. **Store the expression, captures, and lifecycle state in a single heap object:** Simpler indirection structure, but a fixed-capacity cell may be too small to retain captures and later hold the updated representation without resizing or over-allocation.
2. **Reserve enough capacity for the largest possible payload:** Keeps one address but requires predicting capacity, complicates recursive reservation, and may waste simulated heap space.
3. **Reallocate the thunk on update and rewrite all references:** Conflicts with stable shared identity and complicates aliases, recursive captures, and historical snapshots.
4. **Mutate a payload object in place to memoize the result:** Makes snapshot isolation and deterministic replay harder to maintain, since older states may share that object.

## Consequences

### Benefits

- Shared references, including aliases and recursive bindings, retain a stable identity through evaluation and memoization.
- Thunk payload size is independent of the anchor's fixed one-slot capacity.
- Updates do not require patching environments, closures, or other references to the original anchor.
- Immutable payloads and snapshot-isolated cell replacement preserve historical execution states.
- The simulated heap can attribute anchor and payload allocation costs explicitly.

### Obligations and Limitations

- **Administrative overhead:** Every deferred computation introduces an anchor and a separate payload. Those costs must be identified as representation costs when comparing evaluation strategies in B07.
- **Indirection traversal:** Demanding an updated anchor may require following an `Indirection`; the current model performs no path compression.
- **Reclamation:** Successful updates can leave payloads unreachable. They remain allocated until a future garbage collector reclaims them (B12).
- **Capture correctness:** The payload must retain only free local references from its definition site, preserving shadowing and recursive identities without forcing captured bindings.
- **Strategy isolation:** CBV retains strict local-value initialization and nonmemoizing `PendingGlobal` demand; CBN must remain nonmemoizing when implemented in B11.
- **Model fidelity:** This is an explicit experimental heap model, not a claim that GHC or other production runtimes use the same object layout.

## Verification and References

The B05 implementation and integration tests exercise reserved and fresh anchors, selective captures, first demand, memoizing updates, aliases, global and local recursive bindings, and snapshot/batch determinism. See [Core Evaluation Contract, §§7.10–7.11](../core-evaluation-contract.md) for operational rules and the relevant B05 tests for executable evidence.

These tests establish behavior of this interpreter; they do not establish equivalence to GHC's runtime representation or validate the later comparative metrics.

## Revisit When

Revisit this decision if B07 measurements show that anchor/payload overhead obscures meaningful strategy comparisons; if B12 garbage collection requires different reachability or reclamation semantics; if an alternative heap representation can preserve stable sharing and historical snapshots with lower cost; or if subsequent Core/STG integration requires a different layout. Any revision must preserve lexical capture semantics, recursive binding identity, and observable memoization guarantees, or explicitly document the corresponding contract changes.