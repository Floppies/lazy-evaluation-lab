# B07 Audit: Instrumentation and Metrics

Date: 2026-11-14. Formal milestone audit: **B07.11.3**.

## 1. Executive Summary and Verdict

**FIXES NEEDED.** The instrumentation pipeline has substantial positive runtime and regression evidence, but B07 is not ready for integration into main. Two **Medium / Confirmed / Open** production defects prevent supported deep canonical results from being compared or exported to JSON. Both occur after successful, budget-bounded evaluation. A **Low / Confirmed / Open** branch whitespace finding is nonblocking.

The complete suite passed **2,075 tests, zero failures**, both normally and under branch coverage. Overall coverage is **95.34% of executable lines / 87.39% of branch outcomes**. The metrics package is **93.67% / 77.61%**; engine plus runtime is **93.30% / 82.77%**. These separate percentages must not be confused with pytest-cov's combined percentage.

Independent checks covered **1,206 individual transitions across 26 runs**, including heap/stack effects, event increments, stable thunk anchors, limits, all trace modes and 64 retained checkpoints. Additional probes checked checkpoint resumption, multi-span attribution, expected errors, comparability, and actual deep complete/partial results. The two blockers are public comparison/export failures; no wrong evaluator result, changed demand, double accounting or B04–B06 runtime regression was reproduced.

Only this report was created. Production code, existing tests, contracts, specifications, ADRs, planning files and earlier audits were left unchanged. No permanent tests, dependency installation, commit, merge, branch change or pull request was performed.

## 2. Audited Revision, Environment and Methodology

### Revision and environment

| Item | Observed value |
| --- | --- |
| Repository | Floppies/lazy-evaluation-lab, supplied local checkout |
| Branch | `feature/metrics` |
| HEAD | `54e787b0c568f0c916f0198f9ab5b4ed99cf0982` |
| Local main | `34363572aa356b99ca048982f8f1d0145aa3b009` |
| Merge base with local main | `34363572aa356b99ca048982f8f1d0145aa3b009` |
| Initial working tree | Clean; no local modifications or untracked files reported by git |
| Committed branch diff | 45 files, 6,346 insertions, 131 deletions |
| Interpreter | `.venv/Scripts/python.exe` |
| Python | 3.14.3, MSC v.1944, AMD64 |
| Platform | Windows 11, build 26200 |
| Installed tools | pytest 9.1.1; pytest-cov 7.1.0; coverage.py 7.16.2 |

Revision inspection used `git branch --show-current`, `git rev-parse HEAD`, `git rev-parse main`, `git merge-base HEAD main`, `git status --porcelain=v1`, `git log -5 --oneline` and `git diff main...HEAD --stat` / `--numstat`. No fetch was performed, and no assumption was made about remote freshness.

The diff adds eight metrics modules and extends existing evaluator, consumer, heap, stack, thunk, transition and provenance paths. The session runner and constructor materialization algorithm are inherited integrations, not whole modules newly implemented by B07. Core lowering changes chiefly add provenance; the Core node shape remains strategy independent. Current constructor-status corrections in evaluation/Core/ADR documentation are also part of the branch.

### Authority and scope interpretation

Sources reviewed were [AGENTS.md](../../AGENTS.md), [metrics contract](../metrics-contract.md), [technical specification](../specifications/technical-specification.md), [milestones](../planning/milestones.md), the Gantt workbook, [Core evaluation contract](../core-evaluation-contract.md), [Core IR](../core-ir.md), ADR-001/002/003/005/006/007, and the [B05](b05-audit.md) / [B06](b06-audit.md) audits.

The workbook was read with Python's standard-library ZIP/XML tools. Worksheet **Gantt B**, row **19**, assigns B07 instrumentation and metrics, with **22 planned hours**, dependent on B03 and completed with B06. Row **42** specifies comparable metrics, export, and separation of reductions from transitions. It has no per-subtask acceptance cells. The milestone table marks B07.1–B07.10 Completed, B07 In Progress, and B07.11 Pending. These administrative states were preserved.

Technical-specification section 10 delegates operational accounting to the active metrics contract. Its broader roadmap includes optional breakdowns, CBN/STG, GC, lifetime and experimental timing; the current contract explicitly limits implemented accounting. None of those future capabilities is imposed here. The evaluation contract's incremental stage descriptions are read together with its current constructor/materialization section, rather than treating old stage boundaries as missing current features.

ADR-006/007's fixed-capacity anchors and separate payloads remain accepted representation costs. Generated administrative work contributes real operational totals while retaining provenance. No new language-semantic decision or ADR change was introduced.

### Method

Review followed actual producer calls through operational continuations to immutable transition payloads, the reducer and successor instrumentation, rather than checking class existence alone. Tests were inspected for boundary, identity, poison-demand, counter, snapshot and limit assertions. New and edited tests were considered alongside inherited regression coverage.

Independent probes ran through Python stdin, with evaluator/node budgets and bounded harness loops. Temporary in-process observers wrapped the existing accumulation entry points without editing files or changing their returned accounting. Counters were checked against actual heap cells, stack depth, UpdateFrames, explicit event multiplicities and visited-node progress. Deep results were traversed iteratively. Python's recursion limit remained **1,000**.

The independent probes were **excluded from coverage**. A preliminary error probe mistakenly used unsupported source `/`; the lexer correctly rejected it before execution. That harness attempt exited 1 and did not reach its remaining scenarios. The corrected four-error and deep-partial probes completed successfully. This was a probe-input error, not a production regression or a failing pytest test.

## 3. B07 Scope and Contract Compliance

Paths in this table are relative to `src/lazy_lab/`.

| Work package | Assessment | Evidence and qualification |
| --- | --- | --- |
| B07.1 — Contract and accounting | Substantially compliant | Active contract defines six reductions, separate applications/lookups, provenance, baseline, lifecycle, phases, truncation and export. No new semantic conflict found. |
| B07.2 — Data model | Compliant in reviewed internal use | `metrics/state.py`, `events.py`, `effects.py`; frozen records, nonnegative primary counters, typed transition tuples, shared OriginKind. External forged state consistency is not guaranteed. |
| B07.3 — Pure reducer | Compliant in reviewed paths | `metrics/reducer.py:60`; explicit payloads, operational ordering, allocation/baseline/stack validation, derived quantities and immutable updates. |
| B07.4 — Reductions and attribution | Compliant in tested paths | `core/desugar.py`, `metrics/recording.py`, actual evaluator emissions and provenance-preserving continuations. Generated cases/aliases retain their meaning. |
| B07.5 — Heap accounting | Compliant in tested paths | Scoped effects in `runtime/heap.py:89,142,187`; baseline at `engine/core_machine.py:729`. Reserved anchors and payload allocations are distinguished. |
| B07.6 — Stack and phase metrics | Compliant in tested paths | `runtime/stack.py:188,202,227` and ordered reducer processing. Consumer demand frames are included; kind and phase remain separate. |
| B07.7 — CBNeed metrics | Compliant in tested paths | `core_machine.py:901,2105`, thunk-creation callbacks and updated-indirection marker. Per-anchor lifecycle witnesses and pending UpdateFrame accounting pass. |
| B07.8 — Runtime integration | Compliant in tested paths | `metrics/integration.py:13`; evaluator and all eight consumer producers accumulate once. Batch, trace, checkpoint and historical-state checks pass. |
| B07.9 — Comparability | **Incomplete: F01** | Declared factors, truncation, ratios and strategy-only metrics work on shallow results. Valid deep completed results crash automatic assessment. |
| B07.10 — Export | **Incomplete: F02** | Versioned JSON/CSV preserve shallow complete/partial measurements. Deep complete and partial JSON export crashes; CSV remains available. |

This is a scope-limited audit of Core CBV and CBNeed, not certification of STG, CBN, GC/lifetime, UI/replay, HTTP/CLI/database persistence, physical memory, GHC equivalence or scientific campaigns.

## 4. Semantic Event and Attribution Analysis

### Successful operational boundaries

The reducer maps explicit events to counters. It never interprets RuleId to infer reductions, never increments semanticReductions directly, and ignores transition-level source_origins for global event counts.

| Event | Reviewed producer boundary |
| --- | --- |
| FUNCTION_APPLIED / BETA_REDUCED | Effective closure body entry in `core_machine.py:1652,1874`. Both are reported; only beta contributes to semantic reductions. |
| Partial predefined application | `core_machine.py:1582,1844` records one successful unary application, with no beta or seq reduction. |
| Saturated seq | CBNeed records application when accepting the partial function's second argument and SEQ_REDUCED only after first-argument WHNF, at `core_machine.py:1617,1726`. CBV records application and seq reduction after its strict argument protocol at `1805`. |
| LET_ACTIVATED | `core_machine.py:2523` records one group activation, not one per reservation or binding. |
| PRIMITIVE_REDUCED | `core_machine.py:1378` follows successful operand/type/operator execution, including negation. |
| CONDITIONAL_SELECTED | `core_machine.py:2032` follows boolean condition verification and selection. |
| CASE_ALTERNATIVE_SELECTED | `core_machine.py:2407` follows successful selection; subsequent entry into the body does not count again. |
| VARIABLE_LOOKED_UP | `core_machine.py:198` observes an evaluated CoreVar after lookup, excluding internal environment inspections. |

Existing transition tests exercise both strategies, partial/saturated seq, selected and subsequent case transitions, generated provenance and non-exhaustive cases. Independent source runs showed CBNeed partial `seq (1+2)` leaves the primitive unexecuted, while CBV executes it; saturated seq executes it under both. The instrumentation observes the accepted demand policy.

Corrected independent failures used `main = 1 + True`, `main = if 0 then 1 else 2`, `main = 1 2` and `f [] = 0\nmain = f [1]`. They raised three expected TypeErrors and one PatternMatchError. The failing checkpoint retained its instrumentation object, frames and exact heap-cell objects. No successful primitive/conditional/case reduction was accumulated for those failed operations. Earlier successful work, where applicable, remains recorded; this does not invent an exception successor state.

### Provenance

CoreNode.origin defaults to UNKNOWN and is excluded from structural equality independently of SourceSpan. Desugaring explicitly marks original expressions/parameters SOURCE; introduced list chains, temporary pattern lambdas/cases/alternatives and alias groups are GENERATED. Original equation bodies remain SOURCE. Origin metadata does not execute or simplify expressions.

Application/primitive/conditional/case frames and ApplyPrimitive retain the originating Core node across intermediate demand. Application events use CoreApp, beta events use CoreLam, and seq retains its saturating application. Direct Core without provenance remains UNKNOWN. Lifecycle events without a Core node also remain UNKNOWN rather than acquiring a fabricated source origin. INTERNAL is representable; no richer per-origin histogram is promised by the current reducer.

A separate synthetic-payload probe tested **all four origin kinds**, **two SourceSpans per event**, duplicate contextual origins, and a deliberately unrelated RuleId. Each beta event contributed exactly **one beta / one semantic reduction / zero primitive reductions**. This verifies that multi-location provenance does not multiply totals or cause RuleId-based inference.

No confirmed accounting or attribution defect was reproduced in this area.

## 5. Heap, Stack and CBNeed Accounting

### Actual-state accounting

For each of the 1,206 independently observed transitions, checks established:

- currentHeapSlots equalled both Heap.current_slots and the sum of every cell's reserved allocated_slots.
- New heap IDs matched HeapAllocated IDs and the increment in totalAllocations. Existing cells retained their capacities.
- currentFrames equalled the real stack depth. Ordered pushes/pops reproduced final depth and peakFrames, including intermediate depths.
- currentThunkChainLength equalled the actual number of pending UpdateFrames; ordered effects reproduced maxThunkChainLength.
- Evaluator counts matched MachineState.evaluator_transition_count, and evaluator plus consumer counts equalled transition_index.
- Every event increment matched its explicit multiplicity; result-node deltas matched accumulated progress.
- Forced thunks did not exceed created thunks; successful updates did not exceed first forces.

The baseline effect is emitted on the initialization-to-entry boundary, after all global installations. The probe checked the recorded baseline against the actual heap at that boundary. Heap usage is monotonic in the present no-GC model, and replacements do not alter slot totals. The reducer also rejects duplicate/mismatched baselines; its focused tests check these negative paths.

Heap/stack observers are attached to isolated successor containers and released by context managers. Clones do not inherit active observers. Existing tests cover successful and failed captured operations, observer isolation and release. The consumer's field-demand push is captured separately and its evaluator-side pop restores consistent accounting.

### Stable identity and lifecycle

Creation events are emitted after installing a PendingThunk and identify its stable anchor, including initialization into an already reserved cell. Payload allocation remains a separate HeapAllocated event. Beginning force changes that anchor to EvaluatingThunk and pushes an UpdateFrame. Successful WHNF update replaces the original anchor with an Indirection marked from_thunk_update; later demands count a shared hit only for that marked indirection.

Per-anchor checks enforced one creation, one first force, at most one successful update, reuse after update and blackhole reentry before update. Ordinary aliases and CBV indirections do not acquire the marker. The reducer intentionally keeps aggregate counters rather than persistent per-anchor histories.

Representative independent outcomes, using complete materialization unless stated otherwise:

| Source / strategy | Evaluator transitions | Primitive reductions | Shared hits | Thunks forced | Result nodes |
| --- | ---: | ---: | ---: | ---: | ---: |
| `main = let { x = 1+2 } in x+x` / CBV | 38 | 2 | 0 | 0 | 1 |
| Same / CBNeed | 37 | 2 | 1 | 2 | 1 |
| `main = (\x -> 7) (1+2)` / CBV | 29 | 1 | 0 | 0 | 1 |
| Same / CBNeed | 16 | 0 | 0 | 1 | 1 |
| `xs = [1+2]\nmain = [xs,xs]` / CBV | 69 | 2 | 0 | 0 | 9 |
| Same / CBNeed | 67 | 1 | 3 | 8 | 9 |
| `ones = 1 : ones\nmain = ones` / CBNeed, node limit 7 | 40 | 0 | 5 | 4 | 7 |

These counters include globals, fields and administrative runtime representation. For example, three shared hits in the nested-list workload are not three reevaluations of the arithmetic. The simpler x+x workload matches the technical specification's two primitives / one shared-hit oracle.

The local cycle `main = let { x = x } in x` stopped at BLACKHOLE_DETECTED after **16 evaluator transitions**, with no materialized nodes. Reentry counted demand and blackhole without a second force or fabricated update. Pending UpdateFrames remain inspectable at the terminal blackhole. Derived thunksNeverForced and chain depth are distinct quantities.

These are abstract slots, event counts and continuation frames; they are not physical bytes, CPU instructions or host-stack measurements.

## 6. Runtime Integration, Determinism and Snapshots

The evaluator creates one immutable TransitionResult, then calls accumulate_transition_metrics once. The consumer does the same for observation, result-mode selection, atomic materialization, constructor start/advance/complete/limit and field-demand requests. The session runner consumes these successors and does not reduce them again. No separate reduction depends on trace retention.

The 26-run probe checked ten elementary strategy runs, eight shared-tree batch/trace configurations, a blackhole, bounded cyclic output, five evaluator budgets and passive WHNF. Its **64 retained predecessor checkpoints** were inspected again after later execution: instrumentation identity, stack frames and all original cell identities were unchanged.

For `xs = [1+2]\nmain = [xs,xs]` under both strategies, single-transition FULL execution matched batch size **7** under FULL, EVENTS and METRICS_ONLY in accumulated metrics and canonical result. FULL/EVENTS concatenated traces matched the one-step reference; METRICS_ONLY retained no trace. Both strategies count **nine canonical occurrences**, despite CBNeed heap sharing.

A separate checkpoint probe paused the same CBNeed workload at transition **47**, then resumed independent snapshots with batch sizes **1** and **7**. Both matched the uninterrupted **94-transition** result and instrumentation. The original checkpoint retained its metric object and transition index.

WHNF-only `loop = loop\nmain = loop : loop` under CBNeed completed in **11 evaluator transitions plus one consumer transition**, without forcing either field and with **resultNodes = 0**.

### Distinct limit categories

Independent one-transition batches of `main = (1+2) : []` under CBNeed produced:

| Evaluator budget | Status | Final batch stop reason | Total transitions | Result nodes |
| --- | --- | --- | ---: | ---: |
| 1 | RUNNING | EVALUATOR_BUDGET | 1 | 0 |
| 10 | STEP_LIMIT_REACHED | TERMINAL_STATUS | 14 | 1 |
| 11 | STEP_LIMIT_REACHED | TERMINAL_STATUS | 16 | 1 |
| 30 | STEP_LIMIT_REACHED | TERMINAL_STATUS | 38 | 2 |
| 31 | COMPLETED | TERMINAL_STATUS | 40 | 3 |

BATCH_LIMIT exhausted only the current call's total evaluator/consumer capacity and remained resumable. EVALUATOR_BUDGET before root observation retained RUNNING with no invented canonical result. During materialization, unavailable evaluator work led to a published partial result and STEP_LIMIT_REACHED. RESULT_LIMIT_REACHED bounded canonical visits independently; the cyclic example stopped at seven nodes. These statuses and stop reasons are not interchangeable. Increasing a limit does not imply an API promise to resume an already terminal status.

No accounting, snapshot or batch regression was reproduced. The positive evidence is bounded runtime evidence, not a proof for every execution.

## 7. Comparability and Export Verification

### Comparability

The API requires a caller-supplied workload identifier and validates configuration machine/strategy against the state. It evaluates workload, strategy, effective result policy and both limits as explicit factors. ASK_AT_WHNF requires a resolved actual policy. Completed executions with available results are required for complete-cost ratios. Trace mode is intentionally excluded as a logical-cost disqualifier.

An independent `main = [1,2]` comparison observed **26 CBV / 34 CBNeed evaluator transitions**. Without declaring strategy variation, assessment returned different_strategy. With it declared, delta was **-8** and ratio **0.7647058823529411**. A complete/limited pair had **5 / 2 result nodes**, delta **3**, ratio **None**, and only right_not_completed after declaring the node-limit factor. FULL versus METRICS_ONLY was comparable. Comparing thunks_created across CBV/CBNeed raised the expected CBNeed-only ValueError.

Existing tests also check zero denominators, incomplete initial/budget states, mismatched results, policy differences, missing strategy declaration and opaque functions. Partial results are not structurally compared with completed results as semantic mismatches. OpaqueFunction carries no exposed runtime identity and is excluded from automatic equivalence; this exclusion is not proof of function semantics.

The remaining issue is **F01**: automatic equality uses recursive dataclass comparison, and the opaque-tree scan is also recursive. A valid 1,200-element completed list cannot be assessed against an independently produced equal list.

Declared factors allow exploratory cost comparisons. They do not isolate strategy causation, erase representation overhead or establish experimental validity. Workload identifiers/configuration are caller-provided context, not verified source hashes or authenticated provenance.

### Export

RunRecord captures schema version **1**, workload/session IDs, transition index, configuration, effective policy, status, optional stop reason, canonical result and immutable instrumentation. build_run_record reads the measured state; it does not run transitions.

JSON uses explicit kind tags and exports **all 26 primary counters** plus baseline_slots. CSV has **40 stable columns**: 14 metadata columns and the 26 counters with metric_ prefixes. Derived values are reconstructible and need not be duplicated. CSV does not include result trees; an empty collection still produces a header.

Independent exports of the 26 shallow measurements were deterministic for identical records, matched the stored counters in both JSON and CSV, and preserved the measured checkpoint. Existing export tests cover all canonical variants, partial placeholders, optional metadata, CSV escaping and real complete/limited runs under both strategies. Serialization selects canonical data and configuration explicitly; it does not walk heap, stack or environment references. Reading/exporting metrics does not demand evaluation.

**F02** prevents general JSON export of valid supported complete and partial trees. Actual 1,200-element completed results and a 2,401-node partial cyclic observation raised RecursionError in run_record_to_dict and run_record_to_json. CSV of the completed result succeeded. This is separate from persistence/deserialization, which remain outside scope.

## 8. Test Results and Coverage

All pytest commands used the repository interpreter and `-p no:cacheprovider`. Existing ignored caches were not removed. No dependencies were installed.

| Command | Actual result |
| --- | --- |
| `.venv/Scripts/python.exe -m pytest tests/metrics tests/integration tests/runtime -q -p no:cacheprovider` | **746 passed**, 1.99 s |
| `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --cov=lazy_lab --cov-branch --cov-report=term-missing --cov-report=json:$env:TEMP/lazy-lab-b07-audit-54e787b.json` | **2,075 passed**, 7.15 s |
| `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` | **2,075 passed**, 6.59 s |
| `.venv/Scripts/python.exe -m pytest tests/ast tests/frontend tests/core -q -p no:cacheprovider` | **1,024 passed**, 1.34 s |
| `git diff --check` | Exit **0** |
| `git diff main...HEAD --check` | Exit **2**, 11 whitespace diagnostics across seven files; F03 |

These suites overlap and their counts must not be added. Successful pytest runs reported no failing, skipped or xfailed tests. The branch whitespace check and independent crash reproductions are real negative evidence despite the green suite.

For the coverage run, PowerShell set `$env:COVERAGE_FILE = Join-Path $env:TEMP 'lazy-lab-b07-audit-54e787b.coverage'`. Its JSON report and database were written outside the repository; the pre-existing ignored repository .coverage file was not used for these totals.

Coverage was calculated from fresh JSON covered_lines/num_statements and covered_branches/num_branches:

| Scope | Covered / total executable lines | Line coverage | Covered / total branch outcomes | Branch coverage |
| --- | ---: | ---: | ---: | ---: |
| Entire lazy_lab | 3,359 / 3,523 | **95.34%** | 1,192 / 1,364 | **87.39%** |
| src/lazy_lab/metrics | 385 / 411 | **93.67%** | 104 / 134 | **77.61%** |
| Engine + runtime | 1,671 / 1,791 | **93.30%** | 586 / 708 | **82.77%** |

These are whole-module scopes, including inherited code, not changed-line coverage. No invented threshold was applied. The terminal's rounded combined 93% is not the branch percentage.

Important gaps include comparison validation/missing-result/baseline guards and opaque recursion, exporter rejection paths, reducer invalid-allocation/baseline branches, and inconsistent internal evaluator/consumer guards. The ordinary export traversal lines are exercised but **not at the failing depth**. Line coverage therefore does not certify shape coverage. Core-machine coverage still misses 71 lines; consumer coverage misses 19; these figures do not establish defects in the unsupported states those branches reject.

Existing tests contain meaningful expected counter values and real-state invariants. However, the comparison/export tests use shallow trees and omit the newly demonstrated depth regressions. Future regression tests should exercise these public APIs on actual independently produced deep results, rather than relying on recursive test equality.

## 9. Findings, Limitations and Risks

### F01 — Comparing valid deep completed results raises RecursionError

- **Classification:** Production defect introduced in B07's new comparability API; not a B04–B06 evaluator regression.
- **Severity:** Medium. **Status:** Confirmed / Open. **Blocks integration:** Yes.
- **Location:** `src/lazy_lab/metrics/comparison.py:326` / `327`, reached from assess_comparability and compare_metric. Additional recursive scan at `158` / `170`.
- **Evidence / reproduction:** Appendix A runs `rep n = if n == 0 then [] else n : rep (n-1)\nmain = rep 1200` twice under CBNeed, complete materialization, 150,000 evaluator steps and 3,000 result nodes. Both runs complete in **63,638 total / 56,435 evaluator transitions**, with **2,401 result nodes**. Iterative inspection confirms 1,200 Cons cells followed by Nil. assess_comparability(left, right) raises **RecursionError: maximum recursion depth exceeded**, instead of accepting equal completed results. A separate 400-element run pair succeeded, establishing an input-shape boundary rather than a universal failure.
- **Affected contract:** Metrics contract section 7 requires complete same-workload/observation results to be checked and logical metric comparisons to be available under declared conditions. There is no canonical-result depth cap smaller than the supported node budget. ADR-003 also warns callers against recursive deep dataclass equality/tooling.
- **Impact:** Comparing ordinary finite list costs can crash after successful evaluation, including comparisons exposed through compare_metric. This blocks B07.9 acceptance for supported results.
- **Minimal recommended correction:** Use iterative canonical comparison and iterative opaque-function detection while preserving the current opaque-result exclusion, type/tag/field distinctions, completeness gates and mismatch reasons. Fixing equality alone leaves recursive opaque scanning on mismatch paths.
- **Closure:** Equal independent deep results yield a valid assessment; deep unequal results produce the correct mismatch reason; deep opaque-containing results follow the existing exclusion without recursion. Positive-denominator ratios and truncated-result behavior remain covered. Do not increase the global recursion limit or reduce supported result budgets to hide the failure.
- **Historical distinction:** B05/B06 F02 and older audits warned that generic dataclass equality and the test fingerprint recurse. B07 newly calls such equality in a required public production feature; the observed failure is not merely a repeated test-helper limitation.

### F02 — JSON export cannot serialize valid deep complete or partial results

- **Classification:** Production defect introduced in B07's new export API.
- **Severity:** Medium. **Status:** Confirmed / Open. **Blocks integration:** Yes.
- **Location:** `src/lazy_lab/metrics/export.py:153` and `164` recursively convert fields; `207` invokes conversion; `220` performs JSON encoding.
- **Evidence / reproduction:** The two completed 1,200-element runtime results in Appendix A both meet their execution/result budgets. run_record_to_dict and run_record_to_json raise **RecursionError**. CSV succeeds. A separate actual run of `ones = 1 : ones\nmain = ones`, with 30,000 evaluator steps and a **2,401-node result limit**, terminates correctly at RESULT_LIMIT_REACHED after **14,426 total / 7,222 evaluator transitions**. Its partial canonical spine has **1,201 partial constructor levels** and both export functions raise RecursionError.
- **Affected contract:** Metrics contract section 8 promises JSON for complete and partial canonical results, with no additional serialization-depth limit. Core materialization intentionally produces these bounded trees iteratively.
- **Impact:** A valid measurement can be retained and exported as CSV, but its required structural JSON representation is unavailable. This blocks B07.10 acceptance for supported results.
- **Minimal recommended correction:** Convert canonical trees iteratively and make the complete JSON serialization path depth safe. Replacing only _canonical_to_data is insufficient if the standard recursive JSON encoder then fails on the resulting nested dict/list tree. Preserve schema version 1, kind tags, deterministic ordering, partial metadata and passive export.
- **Closure:** Export actual deep complete and partial results without RecursionError, with exact node/value/partial metadata and unchanged counters/state. Validate the JSON structure without relying on a recursively limited oracle. Retain shallow variant, CSV-column and determinism tests.
- **Historical distinction:** General deep-tooling risk was known, but this exporter and its recursive conversion are new in the B07 diff. No B06 runtime failure was observed.

### F03 — The committed branch fails whitespace validation

- **Classification:** B07 change hygiene; no reproduced semantic effect.
- **Severity:** Low. **Status:** Confirmed / Open. **Blocks integration:** No, independently of F01/F02.
- **Locations:** `engine/core_machine.py:400,471,1052`; `metrics/reducer.py:87,209`; `runtime/heap.py:206`; `runtime/stack.py:115,246`; `runtime/transitions.py:177`; `source.py:17`, all beneath src/lazy_lab; and `tests/runtime/test_transitions.py:1733`.
- **Evidence / reproduction:** `git diff main...HEAD --check` exits **2**, with eight trailing-whitespace and three new-blank-line-at-EOF diagnostics. `git diff --check` exits 0 because there was no tracked local patch.
- **Affected check:** The requested Git whitespace verification of the actual B07 changes.
- **Impact:** The branch is not whitespace-clean; this does not explain the runtime/export failures.
- **Minimal correction / closure:** Remove only the reported whitespace in the separately authorized correction phase and rerun the branch-range check.
- **Provenance:** All diagnostics refer to additions in the audited B07 range. No correction was made during the audit.

**Finding totals: Critical 0; High 0; Medium 2; Low 1.** All three are Confirmed and Open. F01/F02 block integration; F03 is nonblocking.

### Explicit separation of other categories

| Category | Disposition |
| --- | --- |
| B07 production defects | F01 and F02, reproduced above. |
| B04–B06 regressions | None reproduced. Existing suites remain passing, supplemented by demand/identity/budget checks. This is not a universal proof. |
| Documentation inconsistencies | No new normative conflict requiring a semantic decision was confirmed. B06 F01's current constructor-status corrections are visible in this branch; historical stage wording remains historical. Planning status reconciliation is administrative, not a semantic defect. |
| Inherited known limitations | B05/B06 F02's recursive fingerprint omits the designated global-environment identity relationship. The helper is unchanged; this audit does not count it as a new B07 finding or rely on it alone for accounting/snapshot evidence. Generic dataclass equality/repr/hash and trusted external-state construction remain bounded-tooling/API concerns. |
| Error/status boundary | Type/pattern errors generally propagate as Python exceptions; no fabricated RUNTIME_ERROR successor is required here. This is inherited behavior, distinct from blackhole and limit statuses. |
| Representation/host costs | Anchor/payload overhead and unreclaimed objects remain real simulated costs; copying containers and analysis add host cost. Aggregate metrics do not isolate causation or native-memory behavior. |
| Future functionality | STG, CBN, GC/reachability/lifetime, detailed unpromised breakdowns, persisted replay/UI, HTTP/CLI/database export, deserialization and scientific benchmark campaigns remain out of scope. |

No suspected defect is promoted to Confirmed merely from an uncovered branch or a hypothetical forged state.

## 10. Recommendations and Closure Criteria

1. Address **F01 and F02 in B07.11.4**, preserving current semantics and public record/schema boundaries. Add focused regression tests for genuinely independent deep complete results, differing deep results/opaque exclusions, and bounded deep partial export.
2. Make traversal depth safe throughout the affected APIs, including JSON encoding. Raising sys.setrecursionlimit, catching the error as a successful comparison/export, or silently truncating supported canonical output would not close these findings.
3. Clean F03 in that correction phase. It does not require an architectural change.
4. Rerun affected metrics/integration tests, the full suite, available branch coverage and `git diff main...HEAD --check` after fixes. Repeat the specific failing probes; do not replace their assertions with shallow equality or merely increase budgets.
5. Reconcile B07 administrative status only after reviewing the fixes and evidence. This report does not update milestones or the Gantt.
6. Retain clear measurement context: complete/truncated status, stop reason, result policy, declared factors, units and representation costs. Treat scientific validity as a later experimental obligation.

No current specification or semantic ADR change is needed to correct these implementation defects. Choosing an additional supported-result depth restriction instead would be a contract decision requiring explicit authorization and documentation; this audit does not make it.

## 11. Merge Readiness Conclusion

**B07 is not ready to merge into main at the audited revision.** F01 and F02 must be closed and verified before acceptance. The failures are localized, correctable comparison/export defects; the evidence does not justify rejecting the overall instrumentation architecture.

Positive static/regression evidence and runtime accounting checks remain valuable, but a green suite does not establish full runtime correctness or experimental validity. The audit applies to the recorded local HEAD and clean starting tree, not to unreviewed later changes.

Artifact ownership: **created docs/audits/b07-audit.md only**. Temporary coverage data was directed to the system temporary directory and both audit measurement files were removed after extracting the totals. The pre-existing repository .coverage was preserved. Final Git status listed only this untracked report; HEAD was unchanged, and the report passed a separate trailing-whitespace/fence/section check. No probe/test source or other project artifact was added.

## Appendix A. Reproducible blocking probes

Run the following Python through `.venv/Scripts/python.exe -` from the repository root. It performs only bounded execution and read-only measurement/export calls. It does not change the recursion limit or print deep dataclass trees.

~~~python
from lazy_lab.pipeline import compile_source
from lazy_lab.engine.core_machine import create_initial_core_state
from lazy_lab.engine.session_runner import run_session_batch
from lazy_lab.metrics.comparison import ComparisonRun, assess_comparability
from lazy_lab.metrics.export import (
    build_run_record, run_record_to_dict,
    run_record_to_json, run_records_to_csv,
)
from lazy_lab.runtime.state import (
    ExecutionConfig, MachineKind, Strategy, ResultPolicy, TraceMode,
)
from lazy_lab.runtime.observation import (
    CanonicalConstructor, CanonicalInteger, CanonicalPartialConstructor,
)
import sys

cfg = ExecutionConfig(
    MachineKind.CORE, Strategy.CBNEED,
    ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
    150000, 3000, TraceMode.METRICS_ONLY,
)
program = compile_source(
    "rep n = if n == 0 then [] else n : rep (n-1)\nmain = rep 1200"
)
runs = []
for label in ("left", "right"):
    batch = run_session_batch(
        create_initial_core_state(program, cfg, session_id=label),
        cfg, max_steps=200000,
    )
    state = batch.state
    value, length = state.canonical_result, 0
    while isinstance(value, CanonicalConstructor) and value.tag == "Cons":
        assert isinstance(value.fields[0], CanonicalInteger)
        length += 1
        value = value.fields[1]
    assert length == 1200 and value.tag == "Nil"
    print(label, state.machine_state.status.value,
          state.transition_index,
          state.machine_state.evaluator_transition_count,
          state.instrumentation_state.counters.result_nodes,
          sys.getrecursionlimit())
    runs.append(ComparisonRun("rep1200", cfg, state))

record = build_run_record(runs[0], stop_reason=batch.stop_reason)
for name, call in (
    ("comparison", lambda: assess_comparability(*runs)),
    ("dict", lambda: run_record_to_dict(record)),
    ("json", lambda: run_record_to_json(record)),
    ("csv", lambda: run_records_to_csv([record])),
):
    try:
        call()
        print(name, "OK")
    except RecursionError:
        print(name, "RecursionError")

partial_cfg = ExecutionConfig(
    MachineKind.CORE, Strategy.CBNEED,
    ResultPolicy.MATERIALIZE_COMPLETE_VALUE,
    30000, 2401, TraceMode.METRICS_ONLY,
)
batch = run_session_batch(
    create_initial_core_state(
        compile_source("ones = 1 : ones\nmain = ones"),
        partial_cfg, session_id="partial-deep",
    ),
    partial_cfg, max_steps=50000,
)
state = batch.state
value, depth = state.canonical_result, 0
while isinstance(value, CanonicalPartialConstructor):
    depth += 1
    value = value.fields[-1]
print("partial", state.machine_state.status.value,
      state.transition_index,
      state.machine_state.evaluator_transition_count,
      state.instrumentation_state.counters.result_nodes, depth)
record = build_run_record(
    ComparisonRun("ones", partial_cfg, state),
    stop_reason=batch.stop_reason,
)
for name, call in (("dict", run_record_to_dict), ("json", run_record_to_json)):
    try:
        call(record)
        print("partial", name, "OK")
    except RecursionError:
        print("partial", name, "RecursionError")
~~~

Observed complete outcomes: both COMPLETED, **63638 / 56435 / 2401 / recursion limit 1000**; comparison/dict/JSON RecursionError, CSV OK. Observed partial outcome: RESULT_LIMIT_REACHED, **14426 / 7222 / 2401 / depth 1201**; dict/JSON RecursionError.

The complete and partial portions were executed as separate stdin probes during the audit. The appendix combines them without changing their workloads or budgets.

## Appendix B. Independent accounting-probe reproduction recipe

The 1,206-transition probe used the matrix below. Each run started with create_initial_core_state(compile_source(source), config), then repeated run_session_batch until the stop reason differed from BATCH_LIMIT. Its harness allowed at most **10,000 batch calls** per run. Unless overridden: Core, complete materialization, **3,000 evaluator steps**, **50 result nodes**, FULL trace and batch size **1**.

| Workload | Strategies / overrides | Run count |
| --- | --- | ---: |
| `main = let { x = 1 + 2 } in x + x` | CBV, CBNeed | 2 |
| `main = (\x -> 7) (1+2)` | CBV, CBNeed | 2 |
| `main = seq (1+2) 7` | CBV, CBNeed | 2 |
| `main = seq (1+2)` | CBV, CBNeed | 2 |
| `f [] = 0\nf (h:t) = h\nmain = f [5]` | CBV, CBNeed | 2 |
| `xs = [1+2]\nmain = [xs,xs]` | Each strategy: FULL size 1; FULL/EVENTS/METRICS_ONLY size 7 | 8 |
| `main = let { x = x } in x` | CBNeed | 1 |
| `ones = 1 : ones\nmain = ones` | CBNeed; node limit 7 | 1 |
| `main = (1+2) : []` | CBNeed; step limits 1, 10, 11, 30, 31 | 5 |
| `loop = loop\nmain = loop : loop` | CBNeed; WHNF_ONLY | 1 |

The following observer is the core independent heap/stack check used in that probe. It can be installed in a temporary stdin process before running the matrix. It preserves the production accumulator, inspects its inputs/successor and returns that successor. Full per-anchor and event assertions are specified immediately below; no permanent test file is needed.

~~~python
from lazy_lab.engine import core_machine as cm, result_consumer as rc
from lazy_lab.metrics.integration import accumulate_transition_metrics
from lazy_lab.metrics.effects import HeapAllocated, StackPushed
from lazy_lab.runtime.stack import UpdateFrame

retained = []
checked = 0

def observed(previous, transition):
    global checked
    machine = previous.machine_state
    metrics = previous.instrumentation_state
    old_cells = dict(machine.heap.cells)
    old_frames = machine.stack.frames
    out = accumulate_transition_metrics(previous, transition)
    state = out.next_state
    next_machine = state.machine_state
    before = metrics.counters
    counters = state.instrumentation_state.counters
    assert previous.instrumentation_state is metrics
    assert machine.stack.frames == old_frames
    assert all(machine.heap.cells[k] is v for k, v in old_cells.items())
    assert counters.evaluator_transitions == next_machine.evaluator_transition_count
    assert (counters.evaluator_transitions + counters.result_consumer_transitions
            == state.transition_index)
    assert (counters.current_heap_slots == next_machine.heap.current_slots
            == sum(cell.allocated_slots for cell in next_machine.heap.cells.values()))
    new_ids = set(next_machine.heap.cells) - set(old_cells)
    allocations = [
        e for e in transition.heap_effects if isinstance(e, HeapAllocated)
    ]
    assert len(new_ids) == len(allocations) == (
        counters.total_allocations - before.total_allocations
    )
    assert new_ids == {e.object_id for e in allocations}
    assert all(next_machine.heap.cells[k].allocated_slots == v.allocated_slots
               for k, v in old_cells.items())
    assert counters.current_frames == next_machine.stack.depth
    assert counters.current_thunk_chain_length == sum(
        isinstance(frame, UpdateFrame) for frame in next_machine.stack.frames
    )
    depth = machine.stack.depth
    chain = before.current_thunk_chain_length
    peak = before.peak_frames
    chain_peak = before.max_thunk_chain_length
    for effect in transition.stack_effects:
        delta = 1 if isinstance(effect, StackPushed) else -1
        depth += delta
        chain += delta * (effect.frame_type == "UpdateFrame")
        peak = max(peak, depth)
        chain_peak = max(chain_peak, chain)
    assert depth == next_machine.stack.depth
    assert peak == counters.peak_frames
    assert chain_peak == counters.max_thunk_chain_length
    progress = next_machine.result_state.materialization
    if progress is not None:
        assert counters.result_nodes == progress.visited_nodes
    assert counters.result_nodes - before.result_nodes == transition.result_nodes_delta
    assert counters.thunks_updated <= counters.thunks_forced <= counters.thunks_created
    if checked % 19 == 0:
        retained.append((previous, metrics, old_cells, old_frames))
    checked += 1
    return out

cm.accumulate_transition_metrics = observed
rc.accumulate_transition_metrics = observed
~~~

The executed harness additionally compared every Core/lifecycle counter increment with a Counter of transition.semantic_events using the contract's one-to-one event mapping; checked the phase-before evaluator-demand subset; and required HeapBaselineRecorded to match the actual initialization heap. Per-run anchor histories were reset at the initial state. THUNK_CREATED required a fresh PendingThunk anchor; THUNK_FORCE_STARTED required its single creation/first force and EvaluatingThunk; THUNK_UPDATED required its single first force/update and Indirection; SHARED_RESULT_HIT required a previous successful update and from_thunk_update; BLACKHOLE_DETECTED required first force without update.

After every run, deterministic JSON and CSV primary counters were compared against asdict(state.instrumentation_state.counters). For the eight shared-tree runs, all instrumentation/results matched the corresponding strategy's size-one reference, and concatenated traces matched except that METRICS_ONLY was empty. After the matrix, all retained checkpoints were checked again by instrumentation and heap-cell identity plus saved frame contents. Actual totals were **26 runs, 1,206 observed transitions, 64 retained checkpoints, all assertions passed**.

Separate supplementary probes used the exact same shared-tree workload at transition 47 for snapshot resumes (batch sizes 1 and 7), the four expected-error sources in section 4, and the finite-list comparability cases in section 7. These supplementary runs and Appendix A are not included in the 1,206-transition count or the measured coverage.

