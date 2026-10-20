@TODO: Make a clenear version

## Lexical Environments

Runtime environments associate variable names with RuntimeRef values.

Each environment contains local bindings and an optional parent
environment. Lookup searches from the innermost scope outward and
returns the stored reference without forcing or dereferencing it.

Extending an environment creates a new scope without modifying
existing scopes.

Recursive groups are constructed after their heap addresses have
been reserved. The environment does not allocate or initialize
heap objects.

Closure capture is handled separately and retains only the
required free local references.

Environment lookup is shared by CBV, CBN, and CBNeed. Strategy-
specific forcing and initialization belong to the evaluator.

## Heap Storage

The runtime uses an explicit simulated heap with monotonically
increasing ObjectIds.

Each HeapCell stores a runtime object and its fixed allocation size,
measured in abstract slots.

Allocation creates a new ObjectId. Replacing a cell preserves its
identity and allocated size. Existing ObjectIds are never reassigned.

Immediate integers and booleans are not stored in the heap.

Heap.get() is a passive operation: it does not force objects or
follow indirections.

Heap.clone() creates an independent copy of the heap state.
Historical execution states must not retain references to a heap
that will be mutated without first preserving the required version.

Garbage collection, forcing, thunk updates, and runtime metrics
are implemented in later milestones.
