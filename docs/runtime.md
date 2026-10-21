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

## Closures and Stack

### Closures

A `Closure` is a runtime heap object that represents a function by combining a `CoreLam` expression with its captured lexical bindings.

Closures capture only the references to free local variables required by the function, rather than the entire definition environment. Global bindings are accessed separately through the global environment.

The `capture_closure()` helper constructs a closure from a precomputed collection of free local names. Computing and validating the actual free-variable set is a responsibility of the future evaluator.

The `call_environment()` method prepares the lexical environment for a function application by extending the captured bindings with the function parameter. It does not execute or evaluate the function body.

Each closure requires one header slot plus one slot per captured local reference.

### Stack

The runtime uses an explicit abstract stack to represent pending evaluation contexts independently of Python's native call stack.

Each `StackFrame` stores only the information required to resume a suspended computation, such as expressions, environments or runtime references.

The initial implementation provides `ApplyFunctionFrame`, `ApplyArgumentFrame` and `IfFrame`. Additional frame types will be introduced alongside their evaluation rules.

The stack follows LIFO ordering and supports `push()`, `pop()`, `peek()` and `clone()`. Cloning preserves an independent sequence of frames for future execution snapshots.

Both closures and stack frames are structural at this stage. Function application, argument evaluation, forcing and other operational transitions belong to later milestones.


## Execution State

The abstract machine state is represented by `ExecutionState`,
which separates semantic execution data from instrumentation.

`MachineState` contains the machine kind, evaluation strategy,
execution status, phase, current control, lexical environments,
heap, stack, and result state.

`InstrumentationState` is reserved for metrics, object history,
and passive analysis. It must not influence semantic transitions.

`ExecutionConfig` defines immutable execution parameters,
including strategy, result policy, trace mode, and execution limits.

Core controls represent pending operations without executing them.
The initial control variants are EvaluateCore, Return, Force,
and InitializeCoreBindings.

### Snapshots

`ExecutionState.snapshot()` creates independent copies of the
mutable heap and stack while preserving logical state identity.

Environments, frames, and current heap object payloads are
immutable and may be shared between snapshots.

Snapshots must remain stable after subsequent execution steps.
Creating a new logical state is separate from copying an existing
one.

Transition rules, tracing, and evaluation are implemented in
later milestones.

## Basic Transitions and Tracing

The Core machine uses a deterministic small-step interface:

`step(state, config) -> TransitionResult`

Each successful transition applies exactly one operational rule and
produces a new logical execution state.

TransitionResult records the applied rule, transition kind, execution
phases, semantic events, and heap/stack effects.

The initial implementation supports only Core integer and boolean
literals. Both return immediate references without heap allocation.

### Execution Limits

MachineState maintains an operational evaluator transition counter,
independent of instrumentation metrics and the global transition index.

The initial batch controller enforces execution budgets and returns
a stop reason. Full public limit-status handling is deferred to B04.

### Basic Tracing

run_batch() executes a bounded number of transitions and collects
lightweight TraceEntry records, except in METRICS_ONLY mode.

Full state retention, event deltas, periodic checkpoints, and replay
are implemented in later milestones.

A root Return with an empty stack is treated as a provisional
observation boundary, not as COMPLETED.

Function application, forcing, recursive initialization, result
materialization, and STG execution are not implemented here.
