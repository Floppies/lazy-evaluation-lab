# Interactive Visualizer Contract

**Status:** Active B08 design contract.  
**Scope:** Interactive Core CBV and CBNeed execution, session coordination, history retention, and passive state inspection. CBN, STG, GC, and object-lifetime visualization are outside the current scope.

## 1. Session Identity and State Separation

An interactive session coordinates one compiled Core program, one immutable `ExecutionConfig`, and one execution run. It does not define evaluation semantics or replace the existing abstract machine.

Each session maintains the following logical components:

- **Session identity:** a unique `session_id` identifying the execution run.
- **Program:** the original source and its compiled Core representation.
- **Configuration:** the execution strategy, result policy, trace mode, and execution limits fixed at session creation.
- **Live head:** the latest `ExecutionState` produced by actual execution.
- **Read cursor:** the logical transition index selected for inspection.
- **History store:** retained execution information according to the configured trace policy.

The controller must distinguish the live head from the read cursor. Moving the cursor selects a historical state for inspection but must not replace, mutate, or rewind the live head.

Execution commands always advance from the live head, regardless of the currently selected historical state. B08 does not support branching execution from historical snapshots.

When the read cursor points to the live head, it may follow subsequent execution automatically. When the user explicitly selects an earlier state, the cursor remains at that position until moved again or explicitly returned to the live head.

`transition_index` identifies a logical position in the execution sequence. `state_id` remains the identity of an individual execution state. These fields must not be treated as interchangeable without an explicit invariant.

Resetting execution, editing the program, or changing execution configuration creates a new run with a new session identity. Historical states are never reused as executable starting points for a new run.

Session navigation and inspection do not produce machine transitions, force references, allocate heap objects, or update instrumentation counters.

The session controller may retain snapshots and metadata in host memory. This storage is separate from the simulated heap and must not contribute to the abstract memory metrics defined in `docs/metrics-contract.md`.

## 2. History Retention and Event-Window Capture

History retention is managed by the interactive session controller according to `ExecutionConfig.trace_mode`.

Retention and inspection must not affect evaluation semantics, transition ordering, result observation, execution budgets, or accumulated metrics.

`TraceEntry` provides lightweight transition metadata but does not retain intermediate execution states or complete instrumentation payloads. Selective capture therefore requires observing actual transitions during execution.

### FULL

`FULL` retains the initial execution state and one snapshot after every successful logical transition.

Every retained state is available for direct historical navigation without re-executing the program.

### EVENTS

`EVENTS` uses selective event-window capture rather than complete execution history or checkpoint-based reconstruction.

The user selects event categories of interest. Supported categories may be defined using existing `SemanticEventKind`, `ExecutionPhase`, `TransitionKind`, and typed heap or stack effects.

For each matching transition at logical index `i`, the controller retains:

- The preceding state, at index `i - 1`.
- The state produced by the matching transition, at index `i`.
- The state produced by the following transition, at index `i + 1`, when available.

This window allows inspection of the selected transition's effects and the immediately following execution step.

Overlapping windows share retained states. A logical state must not be stored more than once for the same session and transition index.

The controller may retain lightweight metadata for transitions outside selected windows, but complete execution states outside those windows are not available for inspection.

Capture filters are initially configured before execution. Filters may be changed while execution is paused, but changes only affect subsequent transitions. Previously discarded states cannot be recovered through historical navigation.

When no following transition exists, the event window remains incomplete. The controller must not synthesize missing states.

`EVENTS` does not reconstruct discarded states through deterministic re-execution and does not implement checkpoint-based replay.

### METRICS_ONLY

`METRICS_ONLY` retains the live execution state and accumulated metrics without retaining a navigable historical state sequence.

Historical navigation is unavailable in this mode.

### Common Invariants

All three modes must produce equivalent logical execution and canonical results for equivalent programs, configurations, and execution commands.

Historical navigation only accesses states that were actually retained. Missing intervals must be represented explicitly rather than presented as continuous history.

Retained snapshots must preserve stable `ObjectId` identities, machine state, control, stack, heap contents, result state, and instrumentation values.

The visualizer may derive differences between retained snapshots for presentation. These differences are not execution events and must not update the simulated machine or its metrics.

History storage and visualization operate in host memory. Their costs are excluded from the abstract heap and execution metrics defined in `docs/metrics-contract.md`.