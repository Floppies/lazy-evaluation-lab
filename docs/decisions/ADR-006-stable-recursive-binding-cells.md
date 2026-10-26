
# ADR-006: Stable One-Slot Anchors for Recursive Local Bindings

- **Status:** Accepted
- **Recorded:** 2026-10-26
- **Scope:** Core runtime, recursive local bindings, heap accounting
- **Related:** ADR-001, ADR-005, B04.6, B07, B12

## Context

Local CoreLetRec groups are mutually recursive.

Every binding must be addressable before its RHS is initialized.
The final runtime value may occupy more heap slots than a
reserved binding cell, especially for closures capturing
multiple local references.

The heap model preserves stable object addresses and does
not resize allocations in place.

## Decision

Reserve one stable, one-slot heap cell per local recursive
binding before evaluating any RHS.

For function-valued bindings:

1. Allocate the actual closure separately, using its exact
   required abstract slot capacity.
2. Replace the reserved binding cell with an Indirection to
   the allocated closure.
3. Keep the original binding reference in the environment
   and in captured recursive references.

The same anchor model will be used when initializing
non-function CBV bindings.

## Rationale

Stable anchors preserve recursive reference identity without
requiring the runtime to predict the final object's size.

Closures may capture references to other group members before
those members are initialized.

The layout separates binding identity from value storage.

## Alternatives Considered

- Reserve maximum closure capacity in advance: requires
  predicting object sizes and may waste abstract heap space.
- Resize heap cells in place: contradicts the current fixed
  allocation model.
- Replace environment references after initialization:
  complicates recursion and invalidates existing captures.

## Consequences

- Local bindings introduce one administrative heap slot
  in addition to their separately allocated values.
- Accessing an initialized binding may require following
  an extra Indirection.
- These administrative costs affect allocation and
  transition metrics.
- Global function installation currently uses a different
  layout, placing one-slot closures directly in reserved
  global cells.
- Comparisons must distinguish these representation costs
  from work caused by the evaluation strategy.
- Future garbage collection must follow references in
  environments, closures and Indirection objects.

This layout is an explicit experimental model, not a claim
that GHC or other production runtimes represent every
recursive binding identically.

## Revisit When

Revisit if measurements show that anchor overhead distorts
the intended comparisons, or if the heap model introduces
alternative representations for recursive values.
