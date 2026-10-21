# B03 audit: Runtime infrastructure, basic tracing, and contracts

Date: 2026-10-21. Scope: B03.1 through B03.6 and the B02-to-B03 boundary. Production code was left unchanged. No evaluator beyond B03 was implemented, and the auditing agent created no commit or branch change.

## Executive summary

**Blocked for clean B03 acceptance and an unconditional B04 handoff, pending F01.** The infrastructure is a suitable basis for B04 on the supported, correctly typed inputs reviewed here. However, three new regression cases expose an existing heap argument-validation defect and remain failing. Fix it in a separately authorized production change and rerun the suite before declaring B03 complete. This is a narrow API robustness blocker, not evidence of incorrect literal evaluation or a need to redesign the runtime.

Verified behavior includes passive lexical lookup, fixed-capacity heap updates, immutable built-in references and payloads, definition-site closure captures, LIFO stacks, independent heap/stack snapshots, deterministic literal transitions, evaluator-budget accounting, bounded batches, and tracing-mode independence for the implemented rules. No valid-input literal execution defect was found. All requested infrastructure areas, including state, stepping, batching, and tracing, are present locally; missing B03.4-B03.6 implementation is not a blocker.

Baseline verification passed **62 runtime/integration tests and 1,182 repository tests**. The audit adds **181 collected test instances** in three new Python files. Final results are **240 passed / 3 failed** for runtime/integration and **1,360 passed / 3 failed** for the complete suite. All three failures reproduce F01; no existing test was changed, weakened, skipped, or marked expected-failure.

Repository coverage is **99.04% lines, 97.01% branches**, or **98.52% combined**. Runtime plus engine coverage is **99.77% lines and 100% branches**. These figures describe executed code paths, including failing regressions. They do not establish a complete evaluator, equivalence among strategies, or experimental validity.

Documentation conflicts and unchecked extension/manual-construction assumptions remain open below. Before B04 implements behavior affected by conflicting specifications, the project owner should explicitly reconcile the contracts. This audit makes no semantic decision on their behalf.

## Scope, repository context, and method

### Local checkout and concurrent change

The first inspection used `Get-Location`, `git branch --show-current`, `git rev-parse HEAD`, and `git status --short` in `C:\Users\flopp\Facultad\PI\lazy-evaluation-lab`.

- Branch: `feature/runtime` throughout the audit.
- Initial HEAD: `325d586bfd22d81d080ecba328f94dc410e91123`.
- Initial working tree: modified `docs/runtime.md`; modified `tests/integration/test_core_runtime.py`; deleted tracked `docs/planning/Gantt_PI_A_B.xlsx`; untracked `docs/planning/gantt.xlsx`.
- During the audit, HEAD advanced externally to **`4f7d88be576e1779462e1e85907d55808c6babad`**, subject `docs: improving runtime md`.
- `git diff --name-status 325d586bfd22d81d080ecba328f94dc410e91123 4f7d88be576e1779462e1e85907d55808c6babad` shows only the 100%-similar Gantt rename and `docs/runtime.md` changes. `git diff` over `src tests` between those commits is empty. The runtime documentation read for this audit already contained the local content subsequently committed.
- The pre-existing integration-test edit adds strategy-mismatch and STG rejection tests. It was included in the baseline and left untouched. No claim is made about remote completeness; no fetch or remote substitution was used.

The final verification therefore applies to the production code shared by both commits, with current local documentation and the pre-existing integration edits. The agent's changes are only the three new test files and this report.

### Sources reviewed

Reviewed local `AGENTS.md`; [language specification](../specifications/language-specification.md); `docs/specifications/technical-specification.docx` version 1.1, especially sections 3-6, 9-10, and 14; [runtime guide](../runtime.md); [Core guide](../core-ir.md); [name-resolution guide](../name-resolution.md); frontend guide and README status; accepted ADR-001 through ADR-005; and [B02.8 audit](b02.8-audit.md).

Actual technical-specification format is DOCX, not a presumed Markdown counterpart. Actual planning path is `docs/planning/gantt.xlsx`. Both Office files were read locally using Python's `zipfile` and XML parser, without modifying or resaving them. No historical auxiliary discussion was used as a normative requirement.

The Gantt's `Gantt B` sheet, row 15, identifies B03 as runtime, traces, and contracts, integrating B02. Row 38 defines its scope as heap, stack, environments, closures, `ExecutionState`, tracing, and limited execution. The workbook provides block-level scope, not individually numbered B03.1-B03.6 acceptance cells. The component mapping below follows the requested audit areas without inventing finer planning requirements. Rows 39-45 distinguish later evaluation, sharing, lists, metrics, visualization, and STG execution work.

Code review covered every module in `src/lazy_lab/runtime/`, `src/lazy_lab/engine/core_machine.py`, the actual `compile_source()` pipeline, relevant Core nodes/validation/desugaring and name checking, and existing runtime/integration tests. Verification combined baseline runs, focused negative and boundary tests, a seeded heap model, deep iterative lookup/compilation, manual extension probes, full-suite execution, and branch coverage.

## Specification and architectural compliance

| Area | Assessment | Evidence and boundary |
| --- | --- | --- |
| References and environments | Verified for built-ins | Exact integer/boolean validation; address-shape validation; dictionary copying; read-only bindings; iterative nearest-scope lookup returning the original reference. |
| Heap | Verified for valid built-in objects; F01 open | Stable increasing IDs, fixed capacity, passive reads, atomic rejected operations, slot accounting and clone independence. Invalid capacity validation is ordered incorrectly. |
| Closures and stack | Structural contracts verified | Local-only captures supplied by caller; definition-site lookup; parameter exclusion; independent call scopes; recursive reference identity; LIFO stack and built-in frozen frames. No application rule is implemented. |
| State | Verified under typed-construction assumptions | Config combinations/limits, distinct status/phase/control, evaluator counter, heap-derived next ID, logical IDs and snapshots. Constructors are not general graph validators: F03. |
| Step | Verified for literal rules | Private selection/application helpers; public successor construction; exact immediate values, rule IDs, counters, unchanged previous state; explicit unsupported boundaries. |
| Batch and basic tracing | Verified at B03 scope | Per-call positive bound, persistent evaluator counter, early stopping, lightweight metadata for FULL/EVENTS, none for METRICS_ONLY. Full history/replay is deferred. |
| B02 integration | Verified as a limited bridge | Real compilation and entry RHS selection, all three Core configurations, multiple globals, no literal allocation, preserved input state. This does not initialize globals. |

[ADR-001](../decisions/ADR-001-core-letrec.md) and [ADR-002](../decisions/ADR-002-pattern-matching.md) still require future operational treatment of recursive groups, aliases and matching. B03 preserves their representational prerequisites without claiming to execute them. [ADR-003](../decisions/ADR-003-iterative-traversal.md) is respected by iterative lookup and the existing compilation traversals; no recursion-limit change was made. [ADR-004](../decisions/ADR-004-source-name-checking-before-desugaring.md) is implemented: `compile_source()` checks all Surface names before lowering, then validates/checks Core. [ADR-005](../decisions/ADR-005-lexical-runtime-environments.md) is structurally supported by name-based lookup and closure call-environment construction; its dynamic acceptance scenarios remain future tests.

## Findings

Finding IDs below are local to this B03 audit. Prior findings are explicitly prefixed with B02.8.

### F01 — Heap allocation compares capacity before validating its type

- **Severity:** Medium; confirmed API robustness defect and clean-sign-off blocker.
- **Location:** `src/lazy_lab/runtime/heap.py:81-92`, `Heap.allocate()`.
- **Reproduction:** `Heap().allocate(Reserved(), allocated_slots=None)` raises Python's comparison `TypeError` at line 84. The same occurs for `"2"`, an opaque object, and a tuple. The dedicated invalid-capacity `ValueError` check at line 89 is never reached. Existing numeric invalid-size tests miss this because their operands are comparable.
- **Regression evidence:** `tests/runtime/test_b03_storage_audit.py::test_invalid_capacity_is_validated_before_comparison[none|string|opaque]`. These are three separate collected cases expecting the already established positive-exact-integer validation boundary. Each starts with a populated heap and checks atomicity in `finally`; all fail solely on the escaping exception type.
- **Impact:** Callers see inconsistent error classes depending on invalid input representation. The payload is consulted before capacity has been established as comparable. No partial allocation, skipped ID, or slot-accounting corruption was observed with the built-ins: the failed operations leave the populated heap unchanged. Valid allocations are unaffected.
- **Recommendation:** Validate `allocated_slots` as an exact positive integer before comparing it with required size. Preserve the current explicit `ValueError` boundary and object-type checks; document the intended order if competing invalid arguments need deterministic precedence. No language-semantics change is needed.
- **Status:** Open, reproduced, production unchanged. Three ordinary failing regressions remain visible; none is suppressed.

### F02 — Heap/frame extension contracts do not enforce their assumptions

- **Severity:** Low for B03; contract risk for extensions.
- **Location:** `runtime/heap.py:13-22, 127-151`; `runtime/stack.py:14-17, 54-58, 72-75`; runtime guide sections 2, 4 and 5. Paths here are under `src/lazy_lab/`.
- **Reproducible evidence:** A custom `HeapObject` with `required_slots` returning `-1`, `0`, `True`, or `1.5` is accepted with capacity 2. Returning `"1"` or `None` instead produces comparison `TypeError`. A mutable subclass with `required_slots = 1` can be allocated and cloned; changing its attribute is visible through both heaps. A mutable custom `StackFrame` is similarly shared by stack clones/snapshots.
- **Impact:** `isinstance(..., HeapObject/StackFrame)` is the only admission check. It does not prove positive exact size, deterministic size, or immutability. Malformed custom sizes do not themselves corrupt the recorded capacity sum in these probes, but invalidate the declared object-size model. Mutable custom instances violate historical isolation assumptions.
- **Supported-input distinction:** Current `Reserved`, `Indirection`, `Closure`, and concrete frame classes are frozen and have appropriate sizes when supplied correctly typed children. The guide explicitly assumes immutable shared payloads and says mutable payloads require revisiting snapshots. No built-in, correctly typed mutation leak was found. Arbitrary mutable subclasses are not established supported snapshot payloads; their acceptance is an unchecked extension precondition, not proof of an existing built-in snapshot bug.
- **Recommendation:** Document or enforce positive exact `required_slots` and immutable graph payloads at the extension boundary. Evaluate size once when validating future custom objects. Use an abstract interface or explicit supported-type policy if appropriate; do not add blanket deep copies of Core/environments without considering identity and cost.
- **Status:** Open contract gap; manual deterministic probes, no production changes and no tests that normalize invalid behavior.

### F03 — Structural state and payload constructors trust most annotated fields

- **Severity:** Low for trusted B03 callers; must be settled before accepting serialized/untrusted states.
- **Location:** `runtime/state.py:105-176`; `runtime/control.py`; `runtime/heap.py:33-48`; `runtime/stack.py:20-36`; `engine/core_machine.py:158-178`.
- **Evidence:** `MachineState` validates only `evaluator_transition_count`; `ExecutionState` validates its own identity fields. Using `dataclasses.replace` can construct an STG/CBV machine, a machine with `phase="invalid"`, or `control=Return([])`. A matching valid Core configuration lets the invalid phase propagate through a literal transition; a root malformed `Return` produces `WHNF_PENDING`. `Indirection([])` is also accepted and shallowly shared by heap clones; mutating that list changes the shared malformed payload.
- **Impact:** Frozen dataclasses prevent reassignment, not type-invalid children. Snapshot safety and observation-boundary classification rely on trusted construction. Invalid annotated values should not be described as supported runtime states. No public state-deserialization path exists here, and these probes do not establish a valid-input execution defect.
- **Verified boundaries:** Config enum fields, machine/strategy combinations, exact positive limits, state IDs, transition indexes, session IDs and evaluator counters have explicit checks, exercised by regressions. `step()` also rejects configuration mismatch and unsupported machine kind before dispatch.
- **Recommendation:** State the trusted typed-construction contract, or add a deliberate validation/factory boundary before API import/session creation. Decide where machine/control/reference consistency belongs instead of assuming all dataclasses already validate it. Preserve support for legitimate phases and future controls.
- **Status:** Open API-contract question. No newly failing test asserts an invented general state-validation guarantee.

### F04 — Technical specification and status/navigation documentation disagree

- **Severity:** Medium as a downstream design dependency; low for stale status/link text alone.
- **Location:** Technical specification sections 2-3 and 6; language specification sections 1, 6-10; ADR-002/004/005; Core guide Overview/Current Limitations; README Status; local `AGENTS.md`.
- **Evidence:** The DOCX specifies `SymbolId` resolution and `Map<SymbolId, RuntimeRef>`; ADR-004/005 and actual code instead use visibility checks and name-based lexical lookup. The DOCX describes sequential `let` plus `let rec`, required special non-referenceable `main`, layout, source `case`, and `seq`; current v0.1 language/ADRs instead have recursive braced `let`, optional ordinary `main`, and a smaller source subset. These are substantive contract differences, not missing B03 evaluator features.
- **Additional drift:** ADR-005 still says implementation pending and its verification prose predates B03; this is only partly current because operational application/recursion remains pending. ADR-002's name-checking question and the agent instructions' B02.9-pending language are superseded by accepted ADR-004 and actual `compile_source()`. The Core guide still calls runtime evaluation wholly unimplemented despite literal stepping. README still focuses solely on frontend/Core construction. The frontend guide's own non-resolution claim is accurate for that package and should not be confused with the separate semantics pipeline.
- **Broken local links:** All five ADRs link to nonexistent `docs/language-specification.md` via `../language-specification.md`. The real target is `docs/specifications/language-specification.md`. From the language specification's current directory, its `decisions/ADR-004-...` and `name-resolution.md` links also point to nonexistent locations.
- **Scope distinction:** Current `docs/runtime.md` accurately describes lightweight FULL/EVENTS tracing and deferred full retention/replay. The DOCX describes their final persistence semantics. This is an explicit milestone limitation, not evidence that B03 must already implement B07/B08.
- **Impact:** A B04 implementer can derive incompatible entry, scope, and binding contracts from different authoritative files. Historical B02.8 evidence must not be mistaken for current runtime results.
- **Recommendation:** Obtain an explicit reconciliation of DOCX versus current v0.1/accepted ADR scope before implementing affected semantics; record accepted decisions and update current specifications/status/links in a separate authorized documentation change. Preserve historical audit findings and dates. The current runtime guide needs no reversion to older claims.
- **Status:** Open; all existing documentation, specifications, ADRs, planning files and agent instructions left unchanged by this audit.

### F05 — Operational aliases, matching policy, and attribution remain unverified

- **Severity:** Medium downstream semantic/experimental risk; not a B03 implementation regression.
- **Location:** ADR-001/002/005 obligations; B02.8 F03/F07; Core guide Constructor inspection and desugaring; empty `InstrumentationState` and transition event/origin placeholders.
- **Evidence:** Reservations can be installed as mutually referring closures and aliases preserve `HeapReference` object identity structurally. No implemented rule initializes recursive groups, forces indirections/thunks/suspensions, executes application/case, or emits attributable work events. Literal transitions have empty semantic events, heap/stack effects, and source origins. Literals contribute an evaluator transition; this is not an arithmetic/beta reduction.
- **Impact:** Infrastructure tests cannot prove CBN nonmemoization, CBNeed at-most-once updates, blackhole handling, strict cyclic initialization, constructor-field demand, original-argument fallback semantics, or source-versus-generated cost neutrality. The non-list scrutinee/default policy remains unresolved in the current Core/ADR contract, while the larger technical specification describes its own type/default rules.
- **Recommendation:** Define and test the relevant operational rules as B04-B06/B11 implement them, and establish provenance/event accounting before B07 metrics or experiments. Preserve original recursive/alias identity and reserve capacity based on eventual captures; do not infer free variables, demand, or sharing from names/spans alone.
- **Status:** Open, intentionally deferred by milestone. It does not independently block infrastructure acceptance; it gates later semantic and experimental claims.

## Detailed correctness assessment

### References and lexical environments

`ImmediateInteger` requires exact `int`, excluding booleans and integer subclasses. `ImmediateBoolean` requires exact `bool`. Arbitrarily large signed integers remain immediate. `HeapReference` requires an exact nonnegative integer and raises `ValueError` for malformed IDs. `ObjectId` is a typing `NewType`, not a separate runtime allocator or runtime class.

Address shape is distinct from heap membership: a well-shaped reference may not have been allocated, and `Heap.get()` checks membership. References contain no session/heap identity, so callers must not mix references from separate heaps merely because their numeric IDs coincide. Reservations intentionally allow environments to contain references before payload installation; safe recursive initialization is still an evaluator responsibility.

`Environment` copies the supplied binding mapping, validates nonempty string names and runtime-reference categories, and exposes a mapping proxy. `extend()` creates a distinct child retaining its lexical parent. Lookup is iterative, chooses the nearest frame, and returns the exact stored reference without heap access. A 4,000-scope test verifies deep nearest-scope shadowing and missing-name failure; the existing test separately finds an outer binding through 2,000 scopes. No recursive environment equality or global recursion-limit workaround was used. The API checks name nonemptiness, not the full Surface identifier grammar; already checked Core identifiers and internal `$` names can use the same lookup mechanism.

### Heap, allocation, and aliases

Allocation starts at ID 0 and increases by one per successful allocation. Replacement preserves object ID and reserved capacity even when the new representation is smaller; no unused slots are reclaimed. `next_object_id` and slot totals remain unchanged on update and on rejected supported operations. Reads return the cell without following an indirection, checking its target's existence, or forcing it. `cells` is a read-only live view, not a detached historical snapshot.

Tests cover invalid object types, malformed/unknown reference arguments, oversized allocation and replacement, fixed cell fields, and atomic failures on populated heaps. A 250-operation deterministic model with seed **20261021** combines allocation, replacement and independent clone allocation while checking every cell's capacity, ID, next ID and total slots. Clones have independent mappings/counters and share immutable cells until replacement. Independent clones can allocate the same next numeric ID in their respective heaps; this is not reuse within one advancing live heap.

The recursive capture/update regression installs a self-referencing closure into a reservation, clones the heap, then replaces the live cell with an indirection. The historical heap retains the closure; both captures keep the original reference; identity/capacity accounting stays unchanged. This demonstrates storage behavior, not an implemented recursive evaluation rule. F01 concerns invalid capacity diagnostics; F02 covers malformed extensions.

### Closures and stack

`capture_closure()` receives preidentified free local names; it does not compute or validate free-variable completeness, or determine whether a supplied name is actually global. For correctly identified names it selects definition-site references, deduplicates/sorts capture names, produces a standalone capture environment, excludes the parameter, and raises `UnboundNameError` for absent captures. Passing a global name in `free_local_names` would capture it: correct local/global classification is a caller precondition, explicitly documented as future evaluator work.

`call_environment()` builds globals, then captured locals, then the parameter. Captured locals shadow colliding globals; the parameter shadows a global with the same name. Calls have independent parameter scopes and retain exact captured reference identity. Uncaptured definition locals are absent. There is no caller-local argument to this API, and no dynamic caller chain is introduced by it. Choosing the actual global environment and evaluating the body are future operational responsibilities.

Stack operations are LIFO, `frames` is an immutable tuple view, invalid pushes raise `TypeError`, and empty peek/pop raise `EmptyStackError`. Clones isolate sequence mutation and preserve shared built-in frame identity. All three concrete frame payload forms were exercised, including `IfFrame`; frozen-field behavior was checked. Arbitrary custom mutable frames fall under F02.

### State and snapshots

`ExecutionConfig` accepts Core CBV/CBN/CBNeed and STG CBNeed, rejects other STG combinations, requires enum instances rather than their string values, and excludes boolean/noninteger/nonpositive limits. STG configuration validity does not imply STG execution exists.

`MachineState` owns semantic control, phase, status, storage, environments and result placeholders. `InstrumentationState` is currently empty and is not read to select execution rules. The evaluator budget counter is semantic operational bookkeeping, independent of `transition_index`. `next_object_id` is read directly from the heap, avoiding a stale duplicated field.

`ExecutionState.snapshot()` preserves logical IDs, session ID and transition index, copies heap and stack containers, and shares environments, controls, result/instrumentation placeholders and immutable built-in payloads. Tests mutate both snapshot and original storage and verify separation. These records are not deeply immutable: consumers can mutate their own heap/stack; retaining a historical record requires avoiding mutation of that retained storage or taking a snapshot. A no-transition batch returns its input state, not a fresh defensive snapshot. Configuration persistence and globally unique state allocation across independent forks/sessions belong to the future runner/controller; `step()` deterministically increments the supplied state ID.

F03 distinguishes malformed dataclass children from supported objects. Deliberate `object.__setattr__`, private-container mutation, cyclic forged environments and type-invalid Core trees are not supported mutation scenarios. No leak was reproduced using normal public mutation of the correctly typed built-in graph.

### Step, batch limits, and error precedence

`_dispatch_core_evaluation()` selects only `CoreInt` and `CoreBool`, with private rule-specific helpers returning `Return` plus `CORE_EVAL_INTEGER` or `CORE_EVAL_BOOLEAN`. Public `step()` validates and coordinates rule application, snapshots mutable storage, increments state ID/transition index/evaluator count once, and constructs `TransitionResult`. Heap/stack contents and phases are retained; literals allocate no heap objects. Tests include nonzero independent IDs/counters, pre-existing heap cells and pending stack content, rather than only empty-state cases.

Observed validation order is explicit:

1. `step()`: machine/config match, Core-only execution, RUNNING status, supported control, evaluator budget, expression dispatch, successor construction.
2. `run_batch()`: exact positive `max_steps`, machine/config validation, then stopping checks before each call to `step()`.
3. Batch stop precedence: **terminal status, root Return with empty stack, evaluator budget, per-call batch bound**. The same checks run after the last permitted step, avoiding an off-by-one BATCH_LIMIT result when observation or budget was reached exactly at the boundary.

Consequently an exhausted `Force` passed directly to `step()` raises unsupported-control error; passed to `run_batch()` it can stop on evaluator budget first. A configuration mismatch is reported even for a terminal input; STG remains explicitly unsupported even when a batch would otherwise stop immediately. These are tested current interface boundaries, not claims about future error-status normalization.

Tests cover bounds 1, 2 and 100 for root literals, consumed budgets, repeated batches at observation boundaries, and a one-step literal with pending stack to distinguish BATCH_LIMIT from EVALUATOR_BUDGET. Resuming an exhausted batch keeps its counter and produces no transition. No synthetic multi-rule evaluator was introduced: every naturally supported root literal reaches observation after one transition. A literal with a pending continuation can consume the batch bound, but processing the resulting Return/frame is unsupported, as expected for B03.

A root `Return` with empty stack yields `WHNF_PENDING`, preserving RUNNING and leaving result materialization unimplemented. It takes precedence over an evaluator limit reached by the same literal step. Direct `step()` on Return still raises unsupported control. No result policy currently performs canonical completion; result-node limits are validated configuration placeholders. All terminal statuses stop batches and reject direct stepping.

### Basic tracing

`TransitionResult` carries rule and transition-kind metadata separately from phase, plus empty effect/origin placeholders for literal rules. `TraceEntry` records IDs/rule/kind/phases without retaining full states. FULL and EVENTS currently collect the same entries; METRICS_ONLY collects none. The trace-mode regression compares control, storage sizes, IDs, counters, phase/status, environments and stop reason, including pre-existing storage. No semantic difference was observed.

There is no B03 metric reducer, object history, checkpoint/delta stream or replay. Empty `InstrumentationState` is an intentional placeholder. Coverage of transition records does not establish future attribution quality or full tracing retention promised for the completed system.

### B02-to-B03 integration

The integration tests use actual `compile_source()` and select the binding named `main`, not the first binding. They compile mutually recursive globals before and after a literal main, preserving the program's binding order while demonstrating that the demo does not evaluate or initialize those globals. Zero, a 101-digit integer, True and False are exercised across all **3 strategies × 3 trace modes**. Immediate wrapper type is exact, its scalar payload is the original Core literal value, heap IDs/slots stay zero, and the earlier state retains the same Core node.

Signed manually built `CoreInt` values also step correctly. Source `-1` lowers to a primitive operation and remains explicitly unsupported: it is not mistaken for an already constructed negative Core literal. Other milestone-specific rejection tests cover variable, arithmetic, recursive let, conditional, lambda, application and list constructors. The function-pattern example also compiles a CoreCase-bearing function, but stepping its main application does not exercise the nested case; direct case dispatch remains unsupported by inspection. A compiled 2,000-term addition tree is rejected by class-name diagnostic without recursively formatting the tree.

New source-name regressions reject unknown references in discarded catch-all/duplicate-constructor equations and an unselected branch even when a literal demo would ignore them. This confirms the ADR-004 boundary and carries forward the resolution of B02.8 F02. It does not turn literal RHS extraction into a program runner or recursive global-environment initializer. Unsupported Core/control and STG tests must be replaced as the corresponding later milestones implement their rules.

## Edge cases, robustness, and coverage interpretation

The three new files are:

| File | Added behavioral coverage |
| --- | --- |
| `tests/runtime/test_b03_storage_audit.py` | Exact scalar/address types; environment input isolation/invalid bindings/deep shadowing; populated-heap failure atomicity; F01 regressions; passive reads/live views; seeded heap model; closure/call/capture boundaries; recursive identity across updates/clones; stack errors and immutability. |
| `tests/runtime/test_b03_execution_audit.py` | Config combinations/limits; state identities/counters; snapshot isolation; nonzero transition bookkeeping; all terminal statuses; deferred controls; batch size/budget/observation precedence; trace equivalence; mismatch/STG errors. |
| `tests/integration/test_b03_audit.py` | Actual compilation with selected main amid recursive globals; literal scalar identity across strategy/trace modes; signed manual Core literals; milestone-specific unsupported expressions; source-name policy; deep compiled rejection. |

There are **181 new collected instances: 178 pass and 3 expose F01**. The original 1,182 baseline tests still pass in the final complete run. The seeded model is a bounded behavioral check, not a performance benchmark or proof for arbitrary operation sequences. No test uses deep dataclass equality, prints a deep Core tree, or increases Python's recursion limit.

Exact final coverage, from the temporary JSON report:

| Scope | Lines | Branch outcomes | Combined |
| --- | --- | --- | --- |
| Entire `lazy_lab` | 1,646 / 1,662 = **99.04%** | 551 / 568 = **97.01%** | 2,197 / 2,230 = **98.52%** |
| Runtime plus engine | 429 / 430 = **99.77%** | 94 / 94 = **100%** | 523 / 524 = **99.81%** |
| `engine/core_machine.py` | 65 / 65 | 28 / 28 | 100% |
| `runtime/heap.py` | 74 / 75 | 10 / 10 | 98.82% |
| Other runtime modules | All executable lines | All existing branches | 100% |

The baseline runtime/engine coverage command reported 407/430 lines covered, with 21 partial branches and **92% combined coverage rounded**. Final coverage gains target meaningful negative/cross-module behavior; they do not justify claiming the exposed bug is fixed.

Uncovered runtime code is `HeapObject.required_slots`'s base `NotImplementedError` at `heap.py:20`. Built-in supported subclasses all override it; directly allocating the incomplete base object is outside their contract. It was not exercised merely to round coverage upward.

Remaining repository gaps are primarily prior static-pipeline guards: desugaring malformed nodes/groups/patterns and defensive branch alternatives; Core validator's non-Core-node walk guard; parser's unrecognized-pattern fallback; and name-checker wrong-root/unsupported node/definition/pattern/alternative guards. Many are excluded by the documented validated-input pipeline; wrong-root public name-checker inputs are still genuinely untested defensive API behavior. Their line numbers are visible in the coverage command output: desugaring 209/227/239/252/341/395; Core validation 334; parser 408; name checking 108/119/137/245/254/360/381. Missing branch outcomes also include desugaring's span-selection and binder-alias paths. No B02 coverage remediation or production edits were attempted.

## Verification commands and observed results

Environment: Windows, repository `.venv\Scripts\python.exe`, **Python 3.14.3**, **pytest 9.1.1**, **pytest-cov 7.1.0**, **coverage 7.16.2**. Versions were read using `python --version`, `python -m pip show pytest pytest-cov`, and coverage JSON metadata. No dependency installation was needed.

All commands below ran from the repository root in PowerShell. Times are pytest-reported host execution durations, not language-runtime benchmark results.

```powershell
# Baseline, before adding tests
.\.venv\Scripts\python.exe -m pytest tests/runtime tests/integration -q
.\.venv\Scripts\python.exe -m pytest -q

# Baseline focused coverage; keep the existing repository .coverage untouched
$env:COVERAGE_FILE = Join-Path $env:TEMP 'lazy-lab-b03-baseline.coverage'
.\.venv\Scripts\python.exe -m pytest tests/runtime tests/integration -q -p no:cacheprovider --cov=lazy_lab.runtime --cov=lazy_lab.engine --cov-branch --cov-report=term-missing

# Final tests
.\.venv\Scripts\python.exe -m pytest tests/runtime tests/integration -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest tests/ast tests/frontend tests/core -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --tb=short

# Final full line/branch coverage, exported outside the repository
$env:COVERAGE_FILE = Join-Path $env:TEMP 'lazy-lab-b03-final.coverage'
$taskCoverageJson = Join-Path $env:TEMP 'lazy-lab-b03-final-coverage.json'
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --tb=short --cov=lazy_lab --cov-branch --cov-report=term-missing --cov-report="json:$taskCoverageJson"

git diff --check
```

| Run | Observed outcome |
| --- | --- |
| Baseline runtime/integration | Exit 0; **62 passed**, 0.10s; one cache warning. |
| Baseline complete suite | Exit 0; **1,182 passed**, 1.84s; one cache warning. |
| Baseline runtime/engine coverage | Exit 0; **62 passed**, 0.20s; 92% combined rounded. |
| Final runtime/integration | Exit 1; **240 passed, 3 failed**, 0.33s. Only F01 cases fail. |
| Final static directories | Exit 0; **1,065 passed**, 1.70s. |
| Final complete suite | Exit 1; **1,360 passed, 3 failed**, 2.07s. Only F01 cases fail. |
| Final complete suite with coverage | Exit 1; **1,360 passed, 3 failed**, 2.51s; coverage report/JSON produced successfully. |
| Final `git diff --check` | Exit 0; no whitespace errors. |
| New-file whitespace checks | `git diff --no-index --check -- /dev/null <path>` ran for all four new files. Each returned 1 for a new-file difference, with only Git's LF-to-CRLF notice and no whitespace-error diagnostics. |

Failure classification: the production behavior in F01 predates the audit; its three failures become visible only through added ordinary regressions. There were no baseline test failures. An initial new integration test mistakenly imported a nonexistent `lazy_lab.semantics.errors` module and caused one collection error; its import was corrected to the verified `lazy_lab.semantics.name_resolution` location before the results above. Intermediate runs before the final two cases were added had 238 focused passes / 3 failures and 1,358 full coverage passes / 3 failures; these are not the final counts.

The baseline warning was `PytestCacheWarning` for a Windows cache path creation failure (`WinError 183`). Later commands disabled only pytest's optional cache provider; the repository cache was not repaired or removed. The tests themselves ran successfully in the baseline. Initial DOCX console printing encountered a host encoding error and was rerun with UTF-8 stdout; extraction then succeeded. Temporary coverage artifacts were written under `$env:TEMP`, not added to the repository. No sandbox/network/dependency failure prevented verification.

## Recommendations not applied and outstanding acceptance criteria

Only the three new test files and this report were created by the agent. Production modules, pre-existing tests, runtime guide, specifications, ADRs, planning/dependency files and `AGENTS.md` were not edited. The external documentation/Gantt commit and the initial integration-test changes are outside the agent's patch.

Before clean B03 acceptance:

1. Correct F01's validation order in a separately authorized production change. Keep the regression cases as ordinary passing tests after repair; rerun runtime/integration, complete suite, coverage and whitespace checks.
2. Record the supported extension and typed-state construction boundaries in F02/F03. Either retain their documented preconditions or deliberately add boundary validation; malformed extension/manual-state probes must not be presented as supported semantics.
3. Reconcile the conflicting binding/entry/language contracts in F04 before B04 implements behavior affected by them. Correct stale current-status prose and local links when documentation changes are authorized. No retroactive rewriting of historical audit conclusions is needed.

For B04 and later acceptance, without requiring their implementation in B03:

- Establish real recursive global initialization and entry selection; test forward references, mutually recursive closures, correct reservation size, source-order strict initialization and cyclic values under the chosen contracts.
- Add free-local analysis and actual application tests: definition-site capture against conflicting caller locals, returned closures, partial applications, independent calls and local/global collisions. Structural call environments alone do not prove these rules.
- Preserve CBN nonmemoization and CBNeed shared thunk/update identity through aliases; distinguish reserved cells, direct aliases and updated results. Implement/test forcing, error categories and cycle/blackhole behavior at their assigned milestones.
- Define non-list case/default behavior before operational matching, and retain first-match/outer-constructor-only inspection and lazy field demand. Carry B02.8 F03 forward until those dynamic tests exist.
- Specify source attribution before metrics/experiments. Carry B02.8 F07 forward; `SourceSpan` and generated-name prefixes are insufficient provenance. Full tracing, event deltas, replay, metrics and object history remain later work.
- Preserve B02.8 F05's explicit manual string-subclass decision boundary and F06's iterative tooling requirement. Frozen Core nodes can still have recursive dataclass equality/repr/hash; deep-tree runtime diagnostics/serialization must avoid those operations.
- Replace B03-specific nonimplementation assertions as B04-B06, B10 and subsequent rules become available. Tests expecting unsupported execution are milestone guards, not permanent language requirements.

**Final assessment:** B03 is substantially implemented and verified for its supported infrastructure and literal-transition subset, but the requested final acceptance remains **blocked pending F01 repair and a clean rerun**. Documentation conflicts need an explicit resolution before affected B04 semantics are introduced. This audit establishes neither full evaluator correctness nor strategy equivalence nor valid experimental cost measurements.

## Follow ups:

### Post-audit follow up (21/10/26):
F01 has been corrected by inverting the order of checks of allocated_slots.
All test created in this audit now succed.
Regarding F02 and F03, the decision is not to implemented verifications everywhere. We keep the following contract: internal runtime objects are constructed by reliable code that respects type and invariants. When another boundary of input gets introduced, like a HTTP API that can create sessions, it will be their responsability to validate data.
F05 for now should be left open because all of the unimplemented logic are not in the scope of B03.

Therefore B03 is considered complete — verified, with documented downstream limitations.