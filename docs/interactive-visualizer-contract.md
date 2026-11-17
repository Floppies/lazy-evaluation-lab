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

Transition observation is provided through an optional synchronous callback at the existing evaluator and session-runner boundaries.

Each successful transition is reported exactly once with its preceding `ExecutionState` and original `TransitionResult`, independently of the configured trace mode.

The observer is read-only and must not mutate machine state, influence evaluation, or produce additional instrumentation events. When no observer is registered, execution behavior remains unchanged.

Explicit result-mode selections performed outside the batch runners must be reported separately by the interactive session controller.

### Event Capture Categories

Five supported capture categories are defined for `EVENTS` mode:

- **`thunks`:** transitions emitting any of the Call-by-Need lifecycle events: `THUNK_CREATED`, `THUNK_DEMANDED`, `THUNK_FORCE_STARTED`, `THUNK_UPDATED`, `SHARED_RESULT_HIT`, or `BLACKHOLE_DETECTED`.
- **`materialization`:** transitions whose `phase_before` or `phase_after` is `RESULT_MATERIALIZATION`.
- **`heap`:** transitions containing `HeapAllocated` or `HeapReplaced` effects. `HeapBaselineRecorded` alone does not qualify as a heap modification.
- **`stack`:** transitions containing at least one typed stack effect.
- **`reductions`:** transitions emitting one of the six semantic reduction events contributing to `semanticReductions`: `BETA_REDUCED`, `LET_ACTIVATED`, `PRIMITIVE_REDUCED`, `CONDITIONAL_SELECTED`, `CASE_ALTERNATIVE_SELECTED`, or `SEQ_REDUCED`.

`FUNCTION_APPLIED` and `VARIABLE_LOOKED_UP` do not independently qualify as semantic reductions.

Category matching examines explicit transition payloads and phase metadata. `RuleId` alone must not imply the occurrence of a semantic event.

A transition may match multiple selected categories. The classifier returns the set of matching categories, allowing the history store to retain one snapshot window with multiple capture reasons.

An empty category selection matches no transitions. Unsupported category names are rejected during session configuration.

Category matching is passive and must not modify the transition, the execution state, or accumulated metrics.

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

#### Event Window Assembly

Selective event-window capture consumes consecutive successful transitions through the existing transition observer.

For a matching transition at logical index `i`, the capture controller retains the preceding state at `i - 1` and the resulting state at `i`. It then requests retention of the state at `i + 1` when the next transition is observed.

The following state is retained even if its transition does not match any currently selected category.

Consecutive matching transitions may open overlapping windows. Shared states are retained only once, using the history store's logical transition indices.

Each selected transition records the set of categories responsible for its capture. These reasons are presentation metadata and do not alter the original semantic events or instrumentation counters.

Changing capture filters applies only to subsequent transitions. A pending successor capture from an earlier event remains valid and must still be completed when its transition occurs.

When execution ends or pauses before a required successor is produced, the window remains incomplete. No missing state is fabricated or reconstructed.

The event-window capture component does not own the live execution state, select result modes, or perform machine transitions. Its integration with session commands is handled by the interactive session controller.

### METRICS_ONLY

`METRICS_ONLY` retains the live execution state and accumulated metrics without retaining a navigable historical state sequence.

Historical navigation is unavailable in this mode.

### Common Invariants

All three modes must produce equivalent logical execution and canonical results for equivalent programs, configurations, and execution commands.

Historical navigation only accesses states that were actually retained. Missing intervals must be represented explicitly rather than presented as continuous history.

Retained snapshots must preserve stable `ObjectId` identities, machine state, control, stack, heap contents, result state, and instrumentation values.

The visualizer may derive differences between retained snapshots for presentation. These differences are not execution events and must not update the simulated machine or its metrics.

History storage and visualization operate in host memory. Their costs are excluded from the abstract heap and execution metrics defined in `docs/metrics-contract.md`.

### Snapshot Storage and Isolation

The interactive history store is scoped to a single execution run and identifies retained states by their logical `transition_index`.

The store accepts explicit snapshot retention requests. The session controller determines which states must be retained according to the configured trace mode:

- In `FULL`, the controller retains the initial state and every successful successor state.
- In `EVENTS`, the controller retains only states required by selected event windows.
- In `METRICS_ONLY`, the history store retains no historical snapshots. The current state and accumulated metrics remain available through the live session.

Retaining an already stored logical state is idempotent. The store must not create duplicate copies for overlapping capture windows.

A retained snapshot is independent of the caller-owned heap and stack. Historical retrieval also returns an independent copy, preventing inspection from mutating the stored state.

States from different sessions cannot be mixed. Conflicting state identities for the same logical transition index are rejected.

Unavailable historical indices produce an explicit lookup failure. The store must not approximate, reconstruct, or silently substitute missing states.

Snapshot retention and retrieval are passive host-side operations. They must not produce machine transitions, update execution metrics, or change the live head.

The history store does not execute transitions or select capture categories. Transition matching and event-window assembly are separate responsibilities.

### Session History Integration and Navigation

The interactive session controller connects execution commands to history retention through the transition observer.

Each successful transition updates the live head and is processed according to the configured retention policy:

- `FULL` retains the successor state for every transition, including explicit result-mode selection.
- `EVENTS` forwards transitions to the selective event-window capture component.
- `METRICS_ONLY` advances the live head without retaining historical snapshots.

The initial state is retained in `FULL` mode when the session is created. In `EVENTS` mode, historical snapshots are retained only when required by selected capture windows.

Explicit `ASK_AT_WHNF` result-mode selections are reported to the history observer even though they occur outside the evaluator and session batch runners.

The read cursor identifies the state selected for inspection. Historical navigation succeeds only when the requested transition index is retained or refers to the current live head.

The live head is always inspectable in every trace mode. Historical inspection returns an independent snapshot and must not modify the live head, heap, stack, instrumentation, or execution configuration.

When historical navigation requests an unavailable state, the controller reports an explicit error and preserves the current read cursor.

Returning to the live head changes only the read cursor.

Event capture filters may be updated while automatic execution is paused. Updated filters apply only to future transitions and do not reinterpret previous capture decisions.

Reset creates a new session identity, a new live state, and an independent history store. Historical snapshots are never reused across execution runs.

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

## 4. Passive State Projections

Visual state projections provide read-only, JSON-compatible
representations of execution states.

Projections must not execute transitions, force thunks,
dereference heap objects through evaluation, modify stack
frames, update instrumentation, or alter the live head.

The projection layer is independent of HTTP endpoints
and frontend components.

### 4.1 Execution Overview

The execution overview exposes:

- Session identity, state identity, and logical transition index.
- The execution configuration, including strategy, result
  policy, trace mode, and execution limits.
- Machine status, phase, and control type.
- Evaluator transition count, stack depth, current heap
  slots, and current heap object count.
- The explicitly selected result mode, when available.
- Whether a canonical result has already been produced.

The overview does not expose mutable runtime objects.
All returned values must be JSON-compatible primitives
or containers.

The control type is reported without recursively
serializing its internal Core expressions or references.
Detailed control and stack projections are defined separately.

The presence of a canonical result is reported without
performing WHNF observation or initiating materialization.

`ExecutionStatus` is preserved independently of
`BatchStopReason`. A projection must not infer a command
stop reason from the machine status.

Projecting the same unchanged state must produce equivalent
output and leave all runtime structures and metrics unchanged.

### 4.2 Control and Stack Projection

The control and stack projection exposes the current
abstract-machine control and its ordered continuation frames.

Control and frame records use explicit type names and
JSON-compatible field summaries.

Runtime references preserve their logical identity:

- Heap references expose stable `ObjectId` values.
- Immediate integers and booleans expose their values.
- References are never forced or dereferenced through evaluation.

Core expressions and alternatives are represented by their
node types without recursively serializing their syntax trees.
Detailed source and Core representations belong to B08.5.

Lexical environments expose only shallow structural metadata.
The projection does not recursively traverse environment
parent chains or inspect referenced heap objects.

Tuple fields may expose their lengths or, for runtime-reference
tuples, their immediate reference values and identities.

Stack frames are ordered from bottom to top. The final frame
is explicitly identified as the top of the stack.

Control and stack projections must be deterministic for an
unchanged state, JSON-compatible, and free of execution effects.

Detailed heap object contents and memory relationships are
handled separately by B08.6.

### 4.3 Metrics and Canonical Result Projection

The metrics and result projection exposes the accumulated
instrumentation and canonical result already present in an
`ExecutionState`.

The metrics representation includes:

- All stored `MetricCounters` fields.
- Derived semantic reductions and current stack frames.
- The number of created thunks that have not been forced.
- The initialization heap baseline and additional peak
  heap usage relative to that baseline.

Derived values use the existing instrumentation properties.
The projection must not recalculate counters from operational
rules or infer metric events from `RuleId`.

Canonical results reuse the existing B07 serialization logic.
Supported values include integers, booleans, opaque functions,
constructor WHNF, complete constructors, pending occurrences,
and partial constructors.

An unavailable canonical result is represented explicitly as
`null`. The projection must not request WHNF observation,
force references, or initiate materialization to produce one.

A result limited by execution or materialization budgets
preserves its existing partial canonical representation.
The projection does not silently treat partial results
as complete results.

Projection output is JSON-compatible and independent of
HTTP or frontend presentation.

Repeated projection of an unchanged state must produce
equivalent output without modifying the simulated heap,
stack, result state, or instrumentation.
