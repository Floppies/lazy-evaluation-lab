# Runtime Infrastructure — B03

**Status:** B03 infrastructure only; not a complete evaluator.

## 1. Runtime References and Lexical Environments

`RuntimeRef` represents immediate integers, booleans, or heap references.

`Environment` maps names to runtime references, with local bindings and an optional lexical parent. Lookup searches from the innermost scope outward and returns a reference without forcing or dereferencing it.

`extend()` creates a new scope without modifying existing scopes. Environments handle visibility and shadowing, not evaluation.

Global bindings and local `CoreLetRec` groups are mutually recursive (ADR-001). Addresses must exist before their right-hand sides are demanded. The evaluator, not the environment, handles allocation and initialization.

Name-based lookup is shared by CBV, CBN, and CBNeed (ADR-005). Initialization, forcing, and sharing are strategy-specific. Compiler-generated names follow the same lexical lookup rules as user-defined names.

## 2. Heap Storage and Allocation

The simulated heap assigns monotonically increasing `ObjectId` values. Each `HeapCell` stores an object and its fixed allocation size in abstract slots.

`Heap.allocate()` reserves slots at a new address. `Heap.replace()` preserves identity and allocation size; the replacement must fit. Updating a cell does not reclaim unused slots.

Each `HeapObject` declares `required_slots`: one for `Reserved` or `Indirection`, and one plus the captured-local count for `Closure`. Required size and allocated capacity may differ.

Immediate values are not heap objects. `Heap.get()` neither follows indirections nor forces computations. A `Reserved` object marks an allocated but not yet initialized cell; an `Indirection` stores another runtime reference.

`Heap.clone()` copies the cell mapping and counters, reusing immutable payloads. GC, thunk updates, and full metrics belong to later milestones.

## 3. Function Closures

A `Closure` stores a `CoreLam` and references to necessary free *local* bindings, not the entire definition environment. Globals are resolved separately.

`capture_closure()` looks up preidentified free local names at the definition site and creates a standalone environment with `parent=None`. It keeps the original `RuntimeRef` objects, including references to reserved recursive cells. Computing and validating free variables remains future evaluator work.

`call_environment()` layers the parameter over captured locals and globals, never over the caller's local scope. It does not evaluate the body.

The lambda parameter cannot be captured. Closure construction does not choose argument evaluation policy.

## 4. Explicit Continuation Stack

The abstract `Stack` is separate from Python's call stack. Immutable `StackFrame` objects hold pending evaluation contexts.

Initial frames: `ApplyFunctionFrame` remembers a pending argument and its environment; `ApplyArgumentFrame` stores a function reference; `IfFrame` retains the branches and their environment. More frames follow their evaluation rules.

The stack uses LIFO order: `push()` adds, `peek()` inspects, and `pop()` removes. `clone()` copies the sequence, sharing immutable frames and environments.

Frames and closures are structural in B03; application and forcing are deferred.

## 5. Execution Configuration and State

`ExecutionConfig` fixes machine kind, strategy, result policy, trace mode, and execution/result limits. Core permits CBV, CBN, and CBNeed; STG-like CBNeed is configured but not executable.

`ExecutionState` carries IDs and transition index, separating `MachineState` from `InstrumentationState`.

`MachineState` holds kind, strategy, status, phase, control, environments, heap, stack, and `ResultState`. `next_object_id` comes from the heap. An operational evaluator counter tracks its execution budget separately from metrics and `transition_index`.

`InstrumentationState` reserves space for metrics and history without affecting semantics. `ResultState` prepares for canonical observation, which is not yet implemented.

### Controls, Phases, and Statuses

Core controls are `EvaluateCore`, `Return`, `Force`, and `InitializeCoreBindings`. Not all have operational rules yet.

Phase, status, and control describe separate dimensions. For example, phase `EVALUATION` can coexist with status `RUNNING`; a `Return` control need not imply a completed program. Successful termination uses `COMPLETED`, not `HALTED`.

### Snapshots

`ExecutionState.snapshot()` retains logical identity but copies the mutable heap and stack. Immutable environments, frames, and heap payloads may be shared.

Snapshots do not advance execution or increment IDs. A semantic step creates a new logical state with an updated ID and transition index. Mutable payloads would require revisiting snapshot isolation.

## 6. Core Transitions and Bounded Execution

The Core machine exposes a deterministic small-step entry point:

```python
step(state, config) -> TransitionResult
```

A successful `step()` selects and applies one rule, creates an independent successor, and reports the `rule_id`, transition kind, previous state ID, phases, and recorded semantic or heap/stack effects in `TransitionResult`. Unsupported constructs raise an explicit error rather than being silently evaluated.

B03 only evaluates `CoreInt` and `CoreBool` into immediate references without allocation. Private rule helpers are coordinated by `step()`.

A root `Return` with empty stack stops provisionally at `WHNF_PENDING` while the machine remains `RUNNING`; canonical completion comes later.

### Execution Limits

`run_batch(..., max_steps=...)` performs at most that many transitions, stopping earlier for pending observation, exhausted evaluator budget, or terminal status. `max_steps` is per call.

The evaluator counter differs from `transition_index`; consumer and GC transitions have separate accounting. Public limit-status handling is deferred.

### Basic Tracing

`TraceEntry` stores lightweight metadata, including source and destination state IDs, rule identifier, transition kind, and phases; it does not retain full states. `run_batch()` collects these records for `FULL` and `EVENTS`, but not `METRICS_ONLY`.

Full snapshots, event deltas, checkpoints, replay, comparable metrics, and object history are deferred.

## 7. B02 Integration and Current Boundaries

B02 produces a validated, name-checked `CoreProgram`. B03 integration tests extract a literal Core expression and pass it to `step()`.

Extracting the `main` RHS in tests is not global initialization. Real execution must initialize recursive bindings and select an entry point.

B03 provides infrastructure, **not** a complete evaluator.

Remaining work: recursive initialization, variables, applications, free-variable analysis, strategy-specific demand/sharing, forcing, result observation, constructors/case, STG-like execution, GC, and metrics.

Core and STG-like machines will share infrastructure but use different operational rules. B04 begins Core evaluation; later milestones add richer semantics, metrics, and STG support.
