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

## 3. Pre-Run Configuration and Session Operations

The interactive application separates program preparation, pre-run configuration, session creation, execution commands, and passive inspection.

No execution session is created until the program and its selected configuration have been validated.

### 3.1 Pre-Run Configuration

Before creating an execution session, the user selects:

- **Program:** source code and an entry binding, defaulting to `main`.
- **Evaluation strategy:** Core CBV or CBNeed.
- **Result policy:** `WHNF_ONLY`, `MATERIALIZE_COMPLETE_VALUE`, or `ASK_AT_WHNF`.
- **Trace mode:** `FULL`, `EVENTS`, or `METRICS_ONLY`.
- **Execution limits:** `execution_step_limit` and `result_node_limit`.
- **Event capture filters:** selected event categories when using `EVENTS`.

Only implemented evaluation strategies may be selected. CBN and STG execution are not supported in B08.

The execution configuration is validated before session creation and remains fixed throughout the run.

Event capture filters are controller-level settings, separate from `ExecutionConfig`. They determine which transitions are retained in `EVENTS` mode without influencing execution semantics.

The number of transitions requested in a batch is a command parameter rather than a fixed execution configuration field.

Changing the program, entry binding, strategy, result policy, trace mode, or execution limits requires creating a new run.

### 3.2 Execution Commands

The controller supports the following logical operations:

- **Compile:** transform source code into validated Core or return compilation diagnostics without executing the program.
- **Create session:** initialize a new run using the selected program, configuration, and event capture filters.
- **Step:** advance the live head by at most one logical transition, including evaluator and result-consumer transitions.
- **Run batch:** execute a bounded number of transitions from the live head, returning the resulting state and stop reason.
- **Pause:** stop requesting additional batches without changing the abstract machine.
- **Select result mode:** record an explicit observation choice under `ASK_AT_WHNF` using the existing `select_result_mode()` operation.
- **Reset:** create a new run from the selected program and configuration.

Automatic execution is controlled through a session-level
`auto_run_requested` flag. Requesting play enables subsequent
bounded batch requests; pausing disables them.

The controller does not schedule background execution.
The client is responsible for requesting further batches
while automatic execution remains enabled.

Automatic execution is disabled when the session reaches a
terminal status, requires an explicit WHNF result-mode
selection, or exhausts its evaluator budget.

Manual step and batch commands remain available while
automatic execution is paused, subject to the existing
execution boundaries.

Execution commands always operate on the live head, independently of the current read cursor.

The controller must preserve the distinction between `ExecutionStatus` and `BatchStopReason`. In particular, `WHNF_PENDING`, `BATCH_LIMIT`, and `EVALUATOR_BUDGET` must not be presented as interchangeable terminal statuses.

An unresolved `ASK_AT_WHNF` choice must not trigger automatic result materialization or additional evaluation.

### 3.3 Passive Inspection

Passive inspection includes selecting retained historical states, navigating the available history, reading machine control and stack frames, inspecting heap objects, viewing source/Core provenance, and displaying accumulated metrics.

These operations must not:

- Execute evaluator or result-consumer transitions.
- Force thunks or follow indirections through evaluation.
- Allocate or replace simulated heap objects.
- Modify execution counters or canonical results.
- Replace the live head with a historical state.

Snapshot differences may be computed for visualization, but they are derived observations rather than machine effects.

### 3.4 Capture Filter Updates

In `EVENTS` mode, capture filters may be modified while execution is paused.

Changes apply only to subsequent transitions and cannot recover previously discarded states.

Changing filters must not alter the execution configuration, instrumentation, or live machine state.

### 3.5 Errors and Execution Boundaries

Compilation failures, invalid configuration, unavailable historical states, invalid commands, and runtime terminal conditions must remain distinguishable.

The controller must respect the existing execution-step and result-node limits.

A terminal execution remains inspectable but cannot be advanced by ordinary execution commands.

The API may translate controller errors into structured responses, but it must not hide terminal states or fabricate successful results.

### 3.6 Scope

B08 provides an in-memory interactive session model with bounded execution and passive inspection.

The contract does not require persistent session storage, branching execution, authentication, distributed workers, or additional evaluation strategies.

Exact HTTP routes, JSON response schemas, and frontend component structure are defined during their respective implementation tasks.