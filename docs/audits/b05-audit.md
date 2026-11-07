# B05 Audit: Call by Need and Sharing

Date: 2026-11-06. Final milestone audit: **B05.11**.
Branch: `feature/call-by-need-evaluator`.
Audited HEAD: `be34b7ee38697ccecd58ea69b3bb61424d7175e1`.

## 1. Executive Summary

**Decision: ACCEPTED WITH LIMITATIONS.** The supported Core Call-by-Need evaluator is ready to integrate into `main`. No reproducible production correctness defect, blocking contract conflict, or architectural obstacle to the subsequent milestones was found. Two **Low / Confirmed / Open** findings concern current implementation-status documentation and the limits of the test fingerprint helper. Neither blocks this merge. Their evidence and closure criteria appear in section 10.

The complete suite passed **1,781 tests**, with zero failures, both normally and under branch coverage. Runtime plus engine coverage is **93.49% of executable lines** and **83.27% of branch outcomes**. These are separate measurements; pytest-cov's rounded **91%** is combined coverage. No acceptance threshold was invented.

Acceptance also rests on tracing the operational rules, reviewing assertions and the branch diff, and independent execution probes. These checked 887 individual evaluator transitions, 10,644 cumulative-budget cuts, 576 chunk configurations, three 2,000-deep Core workloads, expected errors with active thunks, and additional generated expressions. Heap contents, captured references, continuation stages, environment boundaries and historical snapshots were examined, rather than relying on equal results or counters alone.

The implementation follows ADR-007: deferred computations have separate immutable payloads and stable one-slot anchors. Updates occur only after explicit WHNF verification, target the original anchor and preserve capacity. Arguments, global computations and recursive local computations use the same update protocol. Reentrant demand detects a terminal blackhole; ordinary recursion and budget suspension do not automatically do so. Non-strict first-class `seq`, canonical observation and session batching preserve these boundaries. CBV retains its strict application/local initialization and nonmemoizing global protocol.

Only this report was added by the audit. No production code, existing tests, specifications, ADRs, planning files or section 6.5 of the evaluation contract were changed. No permanent audit tests were added: the reviewed suite already covers the critical shallow operational cases, and the additional probes did not expose a critical missing regression. No dependency installation, configuration change, commit, merge or branch change was performed.

This is evidence for the supported runtime subset, not a proof of all executions, complete language support, equivalence to GHC, or scientific validity of future comparative metrics.

## 2. Checkout, Environment and Methodology

### Audited state

The current working tree, including local changes, was inspected. At the start, the only tracked modification was `docs/planning/milestones.md`: B05.6 through B05.10 were changed from earlier administrative states to `Completed`, and B05.11 to `In Progress`. That local version, rather than HEAD's older status table, was used. Its SHA-256 is `41bb51c292affd56b2824d148fc34f8263e24babbba4ffa03e839f9176232f53`.

Local `main` and the merge base were both `01bed878ee03884bcf9c50248af699d25ba7e866`. The committed B05 diff against that base covers 24 files, with 8,903 insertions and 430 deletions. This is contextual change size, not a quality metric. Review included that diff, especially the shared CBV paths and changes to existing tests, as well as the final files. It did not substitute an earlier commit or a remote checkout for the supplied branch. HEAD remained unchanged.

Environment read from the actual interpreter:

| Component | Observed value |
| --- | --- |
| Interpreter | Repository `.venv/Scripts/python.exe` |
| Python | 3.14.3, MSC v.1944, AMD64 |
| OS | Windows 11, build 26200 |
| pytest | 9.1.1 |
| pytest-cov | 7.1.0 |
| coverage.py | 7.16.2 |

### Review method

Review followed each expression and continuation through scheduling, reference return, WHNF demand, consumption and environment restoration. It covered all engine/runtime modules, shared capture/free-variable analysis, the compilation boundary, the B05 integration/runtime tests, pertinent CBV regressions, and the existing audit tests. Assertions were checked against plausible incorrect behavior: premature forcing, reevaluation, dynamic lookup, unresolved updates, partial mutation and incorrect budget accounting.

Independent probes were executed through Python stdin and were not added to the repository or included in the coverage data. Shallow structural comparisons used the reviewed helper alongside explicit anchor, allocation and continuation invariants. Deep probes used an independent iterative graph digest with deterministic encounter indices and backreferences, retaining visited objects to prevent host identity reuse. They also checked that active environments reach the designated global environment **by identity**. They did not use recursive dataclass equality or change Python's recursion limit.

Expected language/runtime errors and documented strict-CBV initialization errors were classified separately from incorrect results. Intentionally inconsistent machine states were used only to test specific defensive boundaries and the sensitivity of test infrastructure. They were not presented as valid programs emitted by the evaluator. This preserves the trusted internal construction boundary accepted in the B03 follow-up.

## 3. Scope and Sources of Authority

The audit covers B05.1 through B05.10 and issues the final B05.11 decision. The governing sources are:

- [AGENTS.md](../../AGENTS.md), including documentation authority, scope, iterative traversal and verification obligations.
- [Core Evaluation Contract](../core-evaluation-contract.md), especially sections 6, 7.9-7.12, 8, 9, 10-15.
- [Technical specification](../specifications/technical-specification.md), including the accepted architecture revision in section 16.
- [Language specification](../specifications/language-specification.md), particularly functions, first-class `seq`, lexical scope and recursive bindings.
- [Milestones](../planning/milestones.md) in their locally modified state and `docs/planning/gantt.xlsx`.
- [ADR-001](../decisions/ADR-001-core-letrec.md), [ADR-005](../decisions/ADR-005-lexical-runtime-environments.md), [ADR-006](../decisions/ADR-006-stable-recursive-binding-cells.md), and [ADR-007](../decisions/ADR-007-separate-thunk-identity-from-evaluation-payload.md).
- [B03 audit and accepted follow-up](b03-audit.md), [B04 audit](b04-audit.md), and the relevant existing module documentation. ADR-003/004 were also consulted through the deep traversal and compilation boundaries.

The local `docs/aux-docs/cbneed-evaluator-construction.md` was consulted as historical construction context. Its early suggestions about placing a thunk behind an anchor, possible one-cell global layouts and unfinished updates do not override ADR-007 or the final operational contract. The ignored auxiliary file was not copied or published by this audit.

The Gantt was read through ZIP/XML without modifying the workbook. `Gantt B`, row 17, assigns B05 26 planned hours after B04; row 40 defines thunks, updates, sharing, blackholes and explicit stack behavior. Rows 18/41 assign executable constructors, case and list recursion to B06; rows 23/46 put deferred nonsharing CBN in B11. The workbook contains no separate B05.1-B05.11 acceptance cells. The operational contract and milestone table provide that detail.

Technical section 16.1 explicitly gives accepted v2.0 revisions precedence over replaced v1.1 passages. Name-based lexical environments, selective local captures, ordinary optional `main`, mutually recursive local `let`, demand-driven globals and first-class curried `seq` were audited as accepted decisions. Historical SymbolId, mandatory-main, sequential-let or nonpartial-seq alternatives were not classified as current implementation defects.

`docs/runtime.md` explicitly retains its B03 historical scope. Its deferred-evaluator statements were not treated as new B05 findings. The protected section 6.5 was read and left unchanged. No semantic decision was introduced or changed during this audit.

## 4. Contract and ADR Compliance

Paths in the following table are relative to `src/lazy_lab/`.

| Work package / obligation | Implementation evidence | Assessment |
| --- | --- | --- |
| B05.1: explicit demand contract | `engine/core_machine.py:145,736,757,926`; contract sections 7.9-7.12 | Evaluation, reference return and forcing are distinct. Operational rules match the supported contract. |
| B05.2: representation and allocation | `runtime/thunks.py:17,50,67,83,111`; `runtime/heap.py:75,119` | Separate payload and one-slot anchor; exact fresh `2 + N` cost; reserved anchors reused. ADR-007 is implemented. |
| B05.3: lazy application | `core_machine.py:1273`; `runtime/closures.py:42`; `runtime/captures.py:12` | Function demanded first; argument deferred at its call site; parameter over captures over globals. ADR-005 preserved. |
| B05.4: forcing continuations | `core_machine.py:790,1808`; `runtime/stack.py:53` | Entry installs an active update frame; initial return requests WHNF; second stage verifies it. |
| B05.5: sharing | `core_machine.py:1808`; `runtime/heap.py:119` | Original anchor updated once to an indirection; result returned directly; aliases not rewritten. |
| B05.6: global/local recursive scope | `core_machine.py:396,446,518,615,1878` | Complete scope reservation precedes installation; non-lambdas deferred; functions installed without executing bodies. ADR-001/006/007 preserved. |
| B05.7: blackholes | `core_machine.py:850`; `step:256`; `_stop_reason:368` | Actual reentrant force with matching active frame is terminal; orphaned evaluating anchor raises an internal-state error. |
| B05.8: `seq` | `core_machine.py:1318,1353,1438`; `runtime/predefined.py` | Partial application is lazy; saturation forces the first argument and returns a fresh second thunk. No `CoreSeq`. |
| B05.9: observation/batches/tracing | `runtime/observation.py:53`; `engine/result_consumer.py`; `engine/session_runner.py` | Passive observation, explicit mode selection, evaluator/consumer accounting and resumable batches remain separated. |
| B05.10: tests/regressions | Six `test_cbneed_*.py` integration modules, runtime thunk/update tests, shared CBV tests and `tests/audits/` | Substantial operational assertions; fingerprint limits recorded in F02. All collected tests pass. |

ADR-006's extra local function anchor and the direct one-slot global closure layout are intentional. They do not violate ADR-007, which governs deferred computations and does not require lambda bindings to acquire thunk payloads. The shared capture helper generalizes the earlier closure-only analysis without changing supported lexical semantics.

No unresolved normative semantic contradiction requiring a design decision was found within B05. The documentation status discrepancy in F01 needs maintenance, not a change to the operational rules or an ADR rewrite.

## 5. Semantic Correctness Analysis

### Application, lexical scope and selective capture

`CoreApp` saves its argument and call-site environment in `ApplyFunctionFrame` before evaluating the function expression. The first return requests `Force`; the frame's `awaiting_whnf` stage prevents confusing a returned reference with a callable WHNF. Non-functions fail before allocating the deferred argument. Under CBNeed, a fresh thunk is then constructed without evaluating its expression. The closure body is entered using its definition-site free-local references and the new argument binding.

`Closure.call_environment()` layers captures over the shared global environment and the parameter over captures. Capture selection visits lexical scopes above the exact global boundary, uses iterative free-variable analysis, sorts names deterministically, and selects references through nearest-binding lookup. It excludes bound lambda parameters and recursive local binders and does not read referenced heap values. "Necessary captures" here means syntactically free local dependencies, not a claim of dynamically predicting which branch will be used.

The suite distinguishes lexical from dynamic lookup through conflicting caller scopes, returned closures, nested argument capture, parameter shadowing and curried applications. Examples include `test_lazy_argument_preserves_call_site_under_shadowing`, `test_returned_closure_preserves_pending_thunk_capture`, and `test_curried_application_preserves_original_capture` in `tests/integration/test_cbneed_application.py:332,459,507`. They inspect actual captured anchors and retained pending values, rather than just accepting a final integer. Independent closure-composition and returned-recursive-function probes also produced the expected values.

### Demand and non-demand contexts

Variable lookup returns the existing reference. Capturing a reference, binding a parameter, creating a pending local RHS, returning a reference or creating `seq a` does not force it. The enclosing continuation determines demand.

Primitive continuations demand operands left to right and restore the original environment between operands. `IfFrame` demands a Boolean condition and evaluates only the selected branch in its original environment. Wrong operand types and wrong condition types fail explicitly. Root observation is preceded by evaluator forcing when the returned reference is pending or indirect; passive conversion does not perform that work.

Existing unused-argument tests use `1 + True` and assert absence of primitive execution; unused-recursion tests retain the original pending object and inspect force targets. These witnesses distinguish laziness from eager evaluation without depending on a timeout. Selection tests leave recursive branches pending. Independent probes exercised unused global cycles and selected predicates as well.

### Failure and snapshot boundaries

`step()` checks configuration/status/budget and obtains `state.snapshot()` before executing mutable rules. Heap clones copy the cell dictionary; stack clones copy the frame list. Cells, built-in heap objects, frames, Core nodes and environments are immutable, with environment mappings copied into read-only views. Replacing a successor cell cannot modify a previous snapshot's cell.

Independent error probes reached failures after 26, 17, 17 and 25 evaluator transitions for, respectively, an invalid primitive through local aliases, application of an integer thunk, a non-Boolean conditional thunk and invalid first-argument `seq` demand. The failed transition's input and every retained predecessor fingerprint remained unchanged. The existing orphaned-update and unresolved-second-stage tests cover additional internal consistency errors. This assurance concerns correctly typed built-in graphs and the explicitly probed errors; it does not certify arbitrary mutable extensions or forged imported states.

## 6. Thunk Lifecycle, Sharing and Memory

### Lifecycle and update discipline

The implemented lifecycle is:

```text
PendingThunk(payload_ref)
    -- Force / CORE_FORCE_THUNK_ENTER --> EvaluatingThunk(payload_ref)
    -- RHS Return / CORE_THUNK_REQUIRE_WHNF --> Force(rhs_reference)
    -- verified WHNF / CORE_THUNK_UPDATE_WHNF --> Indirection(whnf_reference)
```

Entry replaces the original anchor, pushes its `UpdateFrame`, reconstructs captures over globals and schedules the RHS. It allocates no new heap object and does not force a captured dependency. The first return merely advances the frame stage and requests WHNF. Nested forcing pushes another update above the suspended frame; the outer anchor remains evaluating until the inner result reaches WHNF.

At successful update, `_resume_update_frame` verifies the active anchor and WHNF result, replaces the anchor, pops only its update frame, restores its saved caller environment and returns the WHNF reference. Returning that reference directly is necessary: returning the anchor would return an unresolved indirection to a continuation already expecting WHNF. Atomic values, closures and partial predefined functions all fit this protocol.

Tests at `test_cbneed_application.py:1027,1190,1450,1590,1785,1861` distinguish initial return from WHNF, inspect nested frame stages, check LIFO updates, resume function application and associate entry/update transitions with concrete anchors. The repeated-demand witness performs exactly two additions for `(\x -> x + x) (20 + 1)`, retains the original payload and follows an indirection on the second demand. Captured-function reuse tests distinguish sharing a function thunk from calling its body twice.

### Identity, aliases and capacity

Fresh allocation creates a `ThunkPayload` of `1 + N` slots and an anchor of one slot. Preallocated global/local anchors contribute their one slot during reservation; installing the RHS adds only its payload. `Heap.replace()` preserves ObjectId and allocated capacity and rejects oversized contents. Payloads are never installed in undersized anchors. Tests cover fresh allocation, multiple captures, reserved-anchor initialization, repeat initialization rejection, invalid capture atomicity and oversized replacement.

Each source alias binding may have its own anchor and payload because it is itself a binding RHS. Evaluating that alias does not copy the referenced computation: demand reaches the shared target, and each active alias updates its own original anchor after the target reaches WHNF. This is compatible with reference aliases that directly share one anchor. Global and local alias tests assert entry/update targets and stable distinct binding addresses.

Force follows an indirection one edge per transition. It does not compress paths or eagerly rewrite other anchors. The explicit three-link chain test at `test_cbneed_application.py:1706` checks every original target and the exact traversal rules. Updating several active alias thunks to the same final WHNF is their ordinary update protocol, not an extra path-compression pass.

### Retention and accounting

Updated anchors cease to reference their former payloads. Those payloads and other unreachable allocations remain in the heap and slot total. This is the documented no-GC model, not a leak defect within B05. `test_updated_anchor_retains_slots_until_gc` checks a payload with three captured references: four payload slots plus one anchor remain five allocated slots after update.

Independent transition checks verified `current_slots == sum(cell.allocated_slots)`, required capacity bounds, separate payload type/capacity, one-slot anchors, one active frame per evaluating anchor, and at-most-one entry/update per anchor in each execution. Completed executions had matching entered/updated anchor multisets. Blackhole executions correctly retained incomplete updates.

These counts describe the abstract representation. Anchor overhead, predefined startup storage, generated aliases, snapshots and unreachable payload retention must not be equated with source-authored computation or scientific strategy costs. Comparable attribution belongs to B07; collection belongs to B12.

## 7. Globals, Recursion and Blackholes

Global initialization reserves all predefined/user addresses, installs one RHS representation per transition, and only then enters the selected expression. Non-lambda CBNeed globals initialize the existing anchors with thunks whose local captures are empty. Top-level lambdas are direct closures. Forward references therefore have lexical visibility without premature evaluation. Local recursive groups similarly reserve all anchors before installation; local lambdas can capture another member while it is still reserved, and non-lambdas become pending thunks.

`test_cbneed_global_bindings.py` checks reserved-anchor reuse, global sharing across separate calls, forward aliases and untouched recursive globals. `test_cbneed_local_bindings.py:300,450,521` checks capture of not-yet-initialized members, mutual closures and nested shadowing. Independent even/odd recursion actually revisited both functions, and a returned local recursive closure retained its defining parameter. Both terminated normally. No "recursive means blackhole" policy is implemented.

For `Force(EvaluatingThunk)`, the machine searches the active stack for an `UpdateFrame` with the same anchor. If present, it emits `CORE_BLACKHOLE_DETECTED` and changes only status plus ordinary successor counters. Control, heap contents, stack and environments are preserved in independently stored successor containers. If absent, it raises `InvalidMachineStateError`. `test_cbneed_blackholes.py:724` explicitly removes the legitimate frame and checks the error and unchanged state.

Direct and indirect global/local cycles are tested with exact active anchors, force targets and update ordering. Terminal states reject `step()` and return `TERMINAL_STATUS` from batches, even when the evaluator budget is exhausted. Replay of the blackhole predecessor preserves the same context and trace.

Budget stops retain `RUNNING` status and active updates. Increasing the cumulative evaluator limit resumes the same state. The transition that detects a blackhole must actually be allowed to execute: stopping immediately before it reports budget exhaustion, not a blackhole. An independent ordinary recursive program, `loop x = loop x; main = loop 0` on separate source lines, suspended at 150 evaluator transitions with `RUNNING` status and no blackhole event. This is bounded evidence of the distinction, not a termination analysis.

## 8. `seq`, Observation, Batching and Tracing

### First-class `seq`

Dispatch uses the runtime predefined function object, not the spelling of a variable. User-defined global/local/parameter bindings named `seq` follow ordinary closure application. No dedicated `CoreSeq` node is introduced.

For CBNeed partial application, the first expression becomes a thunk retained by `PartialPredefinedFunction`. Its expression and captures remain pending even if demand would fail or blackhole. At saturation, `SeqFirstArgumentFrame` retains the unevaluated second expression and its independent call-site environment while forcing the stored first reference. Only after verified WHNF does saturation allocate the second thunk and return its reference. The receiving context may subsequently demand it.

`test_cbneed_seq.py:165,222` inspects the immediate post-saturation pending second argument, then observes computation or blackhole only after demand. The shared-partial test at line 371 checks one first-argument entry/update across two saturations. The separate-scope and returned-closure tests at lines 558/679 distinguish outer, inner and global references and produce 42/102. A function returned by `seq` is forced and applied normally. Returning a partial `seq` or a closure to WHNF does not execute its retained argument or body.

CBV still evaluates both applications strictly; its stored first argument is already WHNF at saturation. Independent strictness witnesses and retained CBV tests passed. CBN application remains explicitly unsupported and does not acquire thunk updates implicitly.

### Passive canonical observation

`observe_whnf` only converts already-WHNF references. It rejects `Reserved`, `PendingGlobal`, `PendingThunk`, `EvaluatingThunk` and `Indirection`; it neither follows an unresolved edge nor allocates, forces or updates simulated objects. Functions become `OpaqueFunction`; this does not establish extensional equality. The fingerprint's normalization of opaque function results is valid for representation comparison, not mathematical equality of functions.

Fixed `WHNF_ONLY` and `MATERIALIZE_COMPLETE_VALUE` consume atomic/opaque values with one `RESULT_CONSUMER` transition and no additional evaluator work. Materialization records its distinct phase. `ASK_AT_WHNF` waits without progress, then requires one explicit, nonrepeatable selection of a concrete mode before consumption. The original configuration is preserved. Repeated selection and repeated consumption fail.

`transition_index` includes evaluator and consumer work. `evaluator_transition_count` excludes selection/observation. The consumer may complete an already-WHNF result even at the evaluator limit when session batch capacity remains. Batch usage is computed from transition-index differences, so disabling trace retention cannot incorrectly grant extra work. Current values require one result node; recursive materialization and result-node exhaustion for lists remain B06 work.

### Structural equivalence and tracing

`FULL` and `EVENTS` currently retain the same compact `TraceEntry` records; `METRICS_ONLY` retains no entries. These are implemented retention choices, not evidence of full persisted history or rich event deltas. Direct `step()` still returns its RuleId independently of batch trace retention. No mode changes rule selection, heap layout or evaluator budgets.

The later tests at `test_cbneed_observation.py:686,787` strengthen earlier result/counter comparisons by recursively normalizing every dataclass field, heap cell, capture and continuation, including an intermediate state with at least three active updates. That is substantial evidence, with the helper boundary in F02. Earlier smaller projections alone would not establish full structural equivalence.

Independent checks covered every evaluator budget cut in the scenario matrix below, both fixed modes and both ASK selections, all trace modes, and chunk sizes 1, 2, 7 and 19. Resumption reproduced the final normalized state and concatenated trace, and preserved the paused snapshot. Deep graph comparisons additionally preserved environment identity relationships that the repository fingerprint does not encode.

## 9. Test Results and Coverage

### Commands and observed outcomes

All pytest commands used the repository virtual environment and disabled only the optional cache provider. No dependencies were installed. Focused groups overlap and must not be added to the complete-suite count.

| Command | Actual outcome |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` | Exit 0; **1,781 passed**, 3.56s. |
| `.\.venv\Scripts\python.exe -m pytest --cov=lazy_lab.engine --cov=lazy_lab.runtime --cov-branch --cov-report=term-missing --cov-report=json:.coverage-b05.json -q -p no:cacheprovider` | Exit 0; **1,781 passed**, 3.96s; line/branch data exported successfully. |
| `.\.venv\Scripts\python.exe -m pytest tests/ast tests/frontend tests/core -q -p no:cacheprovider` | Exit 0; **1,020 passed**, 1.14s. |
| `.\.venv\Scripts\python.exe -m pytest tests/runtime tests/integration -q -p no:cacheprovider` | Exit 0; **456 passed**, 0.66s. |
| `git diff --check` | Exit 0; no whitespace errors. |
| `git diff --cached --check` | Exit 0; no staged whitespace errors. |
| `git diff --exit-code -- src tests docs/core-evaluation-contract.md docs/specifications docs/decisions docs/planning/gantt.xlsx` | Exit 0; audited implementation, existing tests and governing contracts unchanged by the audit. |
| `git diff --no-index --check -- /dev/null docs/audits/b05-audit.md` | Exit 1 for a new-file difference; only an LF-to-CRLF notice, with no whitespace-error diagnostics. |
| `git status --short` | Only the pre-existing modified milestones file and the new audit report; no staged changes. |

Durations are host test execution times, not language evaluation costs. No skips, xfails or production fixes were introduced. The full-suite count did not increase during the audit. A read-only Markdown file-target scan of the principal current contracts, language/technical specifications, Core guide and four requested ADRs found no missing relative file targets; fragment anchors were not validated. The broken file targets previously recorded in B04 were not reproduced in those current documents.

One initial temporary deep probe used the nonexistent import `lazy_lab.semantics.core_names` and exited before execution. It was corrected to `lazy_lab.semantics.name_resolution.check_core_names`; the successful deep results below come from the corrected runs. The independent graph digest was then hardened to retain visited traversal objects, avoiding host-ID reuse; all three workloads were rerun successfully. Neither setup correction was an evaluator defect or a failing repository test.

### Measured coverage

Coverage includes the whole engine/runtime source scopes and all existing suite tests. Independent stdin probes were not measured. Exact counts came from pytest-cov's JSON summaries.

| Scope | Covered / executable lines | Covered / branch outcomes |
| --- | --- | --- |
| Engine + runtime | 1,191 / 1,274 = **93.49%** | 418 / 502 = **83.27%** |
| Engine | 555 / 627 = **88.52%** | 296 / 370 = **80.00%** |
| Runtime | 636 / 647 = **98.30%** | 122 / 132 = **92.42%** |
| `engine/core_machine.py` | 460 / 518 = **88.80%** | 250 / 310 = **80.65%** |
| `engine/result_consumer.py` | 66 / 78 = **84.62%** | 32 / 44 = **72.73%** |
| `engine/session_runner.py` | 29 / 31 = **93.55%** | 14 / 16 = **87.50%** |
| `runtime/thunks.py` | 58 / 61 = **95.08%** | 19 / 22 = **86.36%** |
| `runtime/captures.py` | 19 / 22 = **86.36%** | 9 / 12 = **75.00%** |

Combined runtime/engine coverage is 1,609 / 1,776 = **90.60%**, displayed as 91%. There are 83 missing lines and 84 missing branch outcomes. No whole-repository percentage is claimed from this scoped run.

Principal gaps and their practical limits:

- `core_machine.py` has 58 missing lines, chiefly invalid control/configuration/index/scope checks, malformed continuation guards, unsupported heap/primitive/predefined fallbacks and inconsistent internal states. CBNeed-specific examples include oversized anchor/wrong payload guards at 803/815, wrong-strategy evaluating thunks at 852, unsupported predefined variants at 1320/1359, `seq` wrong-strategy/unresolved-WHNF guards at 1446/1451, and update wrong-strategy/wrong-anchor/self-update guards at 1816/1825/1856. The self-update branch follows WHNF verification and is unreachable for ordinary correctly constructed evaluating anchors. These gaps limit defensive assurance, without establishing a supported-program failure.
- `result_consumer.py` misses 12 lines: configuration or machine mismatch, invalid phase/control, prepopulated canonical state and inconsistent selection/policy guards. Some are public misuse paths worth testing when an external controller is introduced. The stdin error probes do not increase reported coverage.
- `session_runner.py:38,96` misses invalid batch-size and invalid selected-mode errors. `captures.py:26,29,32`, `closures.py:90` and `thunks.py:35,130,142` miss wrong-type argument guards. `observation.py:61,70,98` misses wrong heap/reference and unsupported object conversion. `heap.py:20` is the abstract size accessor.
- Line coverage is complete for the current control, environment, global-binding, predefined-function, reference, stack, state and transition modules. That does not prove every graph or operational combination correct.

The existing tests have meaningful witnesses for delayed versus eager work, entry/update identity versus recomputation, lexical versus dynamic scope, actual blackhole versus budget suspension and passive conversion versus additional execution. Some earlier batch tests compare only projections; later complete-state tests and the independent checks supplement them. Remaining generic external-state validation, deep-helper robustness and future constructor behavior are not covered by those claims.

### Independent scenario matrix

Each row was compiled and executed under CBNeed. The table uses `;` only to separate top-level definitions for display; the actual source supplied newline separators. Local binding semicolons remain literal syntax.

| Scenario | Source | Expected outcome |
| --- | --- | --- |
| Unused global cycle | `loop = loop; main = (\x -> 42) loop` | 42; cycle unforced |
| Closure composition | `compose f g x = f (g x); main = let { x = 10; f y = x + y } in let { x = 100 } in compose f (\z -> z * 2) 16` | 42 |
| Shared partial | `p = seq (20 + 1); main = p 41 + p 42` | 83 |
| Independent `seq` scopes | `x = 999; main = let { x = 10; p = seq (x + 1) } in let { x = 40 } in p (x + 2)` | 42 |
| Forward local capture | `main = let { f y = x + y; x = 20 + 1; unused = unused } in f 21` | 42 |
| Returned local recursion | `make base = let { go n = if n == 0 then base else go (n - 1) } in go; main = (make 42) 4` | 42 |
| Mutual recursion | `main = let { even n = if n == 0 then True else odd (n - 1); odd n = if n == 0 then False else even (n - 1) } in even 6` | True |
| Predicate demand | `bad = bad; main = let { p = 2 < 3 } in if p then 42 else bad` | 42 |
| Function/partial WHNF | `main = (seq (seq (1 + True)) (\x -> x + 1)) 41` | 42; invalid retained expression unforced |
| Opaque partial | `loop = loop; main = seq loop` | OpaqueFunction |
| Global cycle | `a = b; b = c; c = a; main = a` | BLACKHOLE_DETECTED |
| Second-argument cycle | `main = seq 10 (let { a = b; b = a } in a)` | BLACKHOLE_DETECTED after saturation/demand |

For these 12 programs, independent single-transition checks covered **887 transitions** and retained all predecessors. Maximum simultaneous active updates ranged from one to four. Allocation totals, capacities, active-anchor/frame correspondence and single entry/update per anchor held. The budget matrix covered **10,644 cuts**: every cumulative evaluator count from one through each reference execution's final count, across all three trace modes, two fixed policies and both ASK choices. The chunk matrix covered **576 configurations**: 12 programs x 4 observation choices x 3 modes x 4 chunk sizes. Terminal blackholes require no result selection/consumer work.

### Deep execution and additional probes

Validated, name-checked Core programs were constructed iteratively for three shapes. Each ran continuously and resumed twice from the same budget checkpoint at evaluator count 4,080, with a larger cumulative limit of 100,000. Final evaluator results were `Return(ImmediateInteger(42))`, with empty stacks. Final iterative graph digests matched, paused digests remained unchanged, and paused plus resumed traces equalled uninterrupted traces.

| Shape / reproducible construction | Depth | Active updates at checkpoint | Final evaluator transitions | Final allocated slots |
| --- | --- | --- | --- | --- |
| Start at `CoreInt(42)`; wrap repeatedly in `CoreApp(CoreLam("x", CoreVar("x")), expression)` | 2,000 | 453 | 20,010 | 6,003 |
| Start at `CoreInt(42)`; wrap repeatedly in `CoreLetRec((CoreBinding("x", expression),), CoreVar("x"))` | 2,000 | 583 | 16,010 | 4,003 |
| `main -> a1 -> ... -> a2000 -> 42`, each a global binding | 2,000 edges | 692 | 10,010 | 4,003 |

These are evaluator-only runs ending at `WHNF_PENDING`; they do not include a result-consumer transition. They directly exercise deep suspension/forcing and numerous pending continuations, beyond the shallow checkpoint tests. No generic recursive equality was used.

A supplementary seeded source generator (`random.Random(0xB05)`, depth four, 250 expressions) tracked expected integer values while composing literals/visible variables, arithmetic, conditional selection, shadowing lambda application, fresh local bindings, forward aliases and `seq` with a function in WHNF. All **250 CBNeed results** matched the independently computed values. On the same programs, **24 CBV executions** completed with the same values; **226** reached the documented strict local forward-initialization error. Those expected errors are not equivalence successes or defects. This temporary generator is supplementary bounded evidence, not an archived property-testing framework or coverage result.

Four further CBV witnesses required type errors for an unused invalid ordinary argument, an unused invalid local binding, invalid `seq` partial argument and invalid saturated second argument. Repeated CBV global demand executed the global addition twice plus the result addition and retained `PendingGlobal`. CBN ordinary application raised `UnsupportedTransitionError`. These observations agree with the branch-diff review and retained CBV regressions.

## 10. Findings, Limitations and Risks

### Production defects

**None confirmed in the supported B05 program/state boundary.** No Critical, High or Medium finding was established. No suspected production defect is being substituted with a documentation recommendation. In particular, separate payload overhead, unreachable allocations, nonstrict partial `seq`, direct global closures and current compact trace retention follow accepted contracts or explicit milestone boundaries.

### F01 — Current implementation-status prose lags the implemented CBNeed subset

- **Category:** Documentation / maintenance debt.
- **Severity:** Low. **Status:** Confirmed / Open. **Blocks merge:** No.
- **Locations:** `docs/core-evaluation-contract.md:3,5,54,265`; `docs/core-ir.md:7,198,259`; `docs/decisions/ADR-005-lexical-runtime-environments.md:3,82`; `src/lazy_lab/engine/core_machine.py:1,761,1278`.
- **Evidence:** The current contract overview describes CBV implementation and CBNeed contracts, while sections 7.11, 13.5 and 14.5-14.6 document implemented CBNeed transitions. The Core guide still defers non-strict evaluation; ADR-005's implementation note still calls it future work. `_advance_force` says it does not implement thunk updates, and `_resume_apply_function` describes only strict CBV scheduling, despite their CBNeed paths. Fresh execution exercises the implemented behavior. The old broken relative file targets reported by B04 were not reproduced by the scoped file-target scan.
- **Impact:** A maintainer can underestimate the supported runtime or follow obsolete incremental status text. No demand/sharing error follows from these descriptions.
- **Recommended correction:** In a separately authorized documentation maintenance change, reconcile current status overviews and module docstrings with the supported CBV/CBNeed subset and link this audit as evidence. Preserve historical records and accepted decisions; no semantic ADR replacement is needed. Leave the explicitly protected section 6.5 unchanged under this task.
- **Planning distinction:** HEAD's B05.6-B05.10 administrative statuses are stale, but the user's existing local changes already mark them completed. The local B05/B05.11 `In Progress` entries appropriately remain pending final administrative closure. This report does not silently mark them completed or treat that maintenance as an evaluator defect.
- **Closure criterion:** Current status/navigation accurately distinguishes implemented CBNeed, deferred CBN/constructors and historical snapshots; separately review the final planning status. No production behavior needs changing for F01.

### F02 — Structural fingerprint omits the identity-based global boundary and is recursive

- **Category:** Test infrastructure debt / assurance limitation.
- **Severity:** Low. **Status:** Confirmed / Open. **Blocks merge:** No.
- **Locations:** `tests/helpers/runtime_equivalence.py:12,46,63,76`; identity-sensitive consumer at `src/lazy_lab/runtime/captures.py:40`.
- **What it covers:** Every current dataclass field is visited, including `eq=False` closures, payloads and environments. Heap IDs, slot totals, next ID, cells, expressions, captured references, frame payloads/stages, environment parent contents, control, results, status, phase and counters are retained. Unknown types fail explicitly. Sorting mappings makes entry order immaterial while stable heap references remain visible. It does not erase allocation IDs or compare only counters.
- **Confirmed limitation:** Structurally equal but distinct environment nodes normalize equally. The machine's capture selector uses `current is global_environment` as its boundary, so the relationship to that designated object matters. A fingerprint equality assertion alone cannot detect its accidental duplication. In addition, recursively visiting a 2,000-deep Core lambda produces `RecursionError` even though the relevant runtime/free-variable operations are iterative.
- **Reproduction:** After executing `main = 42` to WHNF, replace control with `EvaluateCore(CoreLam("x", CoreVar("x")))`, obtaining state `a`. Let `g = a.machine_state.global_environment`; construct `b` by replacing only `global_environment` with `Environment(g.bindings, g.parent)`, leaving the local environment pointing to the original. `runtime_fingerprint(a) == runtime_fingerprint(b)` evaluates to **True**. `step(a, config)` emits `CORE_EVAL_LAMBDA`; `step(b, config)` raises **ValueError: Global environment is not an ancestor of the definition environment**. For depth, start at `CoreInt(0)`, wrap 2,000 times with `CoreLam("x", expression)`, and fingerprint it: **RecursionError**.
- **Interpretation:** State `b` is intentionally inconsistent; this is a sensitivity test for the helper, not evidence that the evaluator produces it or an expansion of the trusted-state contract. Independent deep probes checked the actual boundary relations and used a separate iterative graph encoding; no duplicated-boundary execution was found. Existing tests also contain explicit `is` assertions for caller restoration and capture identity.
- **Impact:** Claims of exhaustive graph equivalence based solely on this helper would be too strong. It also cannot support future arbitrary-depth equivalence tests in its current form.
- **Recommended correction:** Add explicit global-ancestor identity invariants to equivalence/checkpoint tests, or encode this designated relationship with normalized graph identities. Use iterative traversal for deep values. Arbitrary immutable Python object sharing need not become a language invariant. Add a sensitivity test when changing the helper.
- **Closure criterion:** A duplicated designated global boundary is rejected or distinguished, meaningful field changes still differ, and a validated deep Core graph normalizes without host recursion. This improvement is useful for later replay/serialization work, but current B05 acceptance has independent evidence for those boundaries.

Finding totals: **Critical 0; High 0; Medium 0; Low 2**. Both are confirmed nonblocking debt, left open. No finding is marked fixed during this audit.

### Accepted limitations and future integration risks

| Boundary | Consequence / future obligation | Classification |
| --- | --- | --- |
| Trusted built-in state construction | Import/API boundaries must validate external graphs, references and immutable payload assumptions. Snapshot isolation does not promise arbitrary mutable extension safety. | Inherited B03 contract; future integration risk |
| No constructors/case execution | Constructor WHNF, non-list matching/default behavior, lazy fields and recursive materialization need explicit B06 rules/tests. | B06, outside scope |
| No comparable instrumentation | Current transition/slot counts include administrative layout costs. Source provenance, sharing-hit attribution and comparable reductions need B07 definitions. | B07, outside scope |
| Compact traces; no persisted replay system | FULL/EVENTS currently retain equal compact entries. Source origins, heap/stack effects, history/checkpoints and UI replay require later work. | B07/B08, outside scope |
| Same Core, separate strategies | CBN application/local initialization remain unsupported. Its future suspensions must not inherit CBNeed updates; STG requires its own lowering/rules. | B09-B11, outside scope |
| No garbage collection | Unreachable payloads remain counted. Future roots must include active update anchors, payload captures, closure captures, partial arguments, saved frame environments and pending second expressions. | B12 dependency risk, not B05 defect |
| Host storage copying and repeated analysis | Each transition copies heap/stack containers, and allocating nested deferred expressions repeats free-variable analysis. Large host costs are possible and were not benchmarked here. | Performance/experimental interpretation risk |
| Deep generic tooling | Core dataclass equality/repr/hash and this recursive fingerprint have host-recursion limits; operational stepping does not inherit that limitation in the tested shapes. | Existing tooling risk; F02 for helper |
| Error/status boundary | Supported runtime errors generally propagate as Python exceptions. A future controller must map them deliberately without rewriting failed checkpoints or conflating limits and blackholes. | Inherited API limitation |

Optional improvements include moving test utility imports out of integration test modules, extending defensive misuse coverage as those APIs evolve, and retaining a reusable generated-program/graph-invariant harness. None is a required production refactor for this merge. Object-lifetime visualization and the experimental campaign remain B13-B16; operational GHC equivalence and metric validity are not certified.

## 11. Recommendations and Closure Criteria

1. Integrate the audited B05 implementation after normal repository review. There is no reproduced production fix required by this audit. Preserve the current anchor/payload model and common forcing/update path when extending the machine.
2. Track F01 and F02 as nonblocking follow-ups with their concrete closure criteria. Do not rewrite specifications to justify a future wrong result, erase historical ADRs, or treat shallow fingerprint equality as complete graph verification.
3. Reconcile administrative B05/B05.11 status after accepting the report. Preserve the user's current local planning patch until that decision is recorded; this audit has not modified it.
4. Before B06, specify constructor/default errors and field demand, and extend the update/observation invariants to constructor WHNF. Preserve lazy fields, recursive captures and first-match semantics.
5. Before B07/B12, define source versus administrative attribution and GC roots for every new payload/frame. Keep allocation identity, passive observation and snapshot preservation explicit. No new B05 semantic ADR is currently needed.
6. If production code or accepted contracts change before merge, rerun relevant tests, the complete suite, scoped branch coverage and the affected independent scenarios. This verdict applies to the recorded HEAD plus supplied local state, not an unreviewed later revision or a changing remote `main`.

Audit artifact ownership: **created `docs/audits/b05-audit.md` only**. The pre-existing `docs/planning/milestones.md` modification was preserved. The temporary `.coverage-b05.json` export was removed after extracting its totals; `.coverage` is an ignored measurement artifact. No temporary probe source or new test file is part of the patch. Production, specifications, ADRs, existing tests, the Gantt and historical audits remain unchanged.

## 12. Merge Readiness Conclusion

**ACCEPTED WITH LIMITATIONS — B05 is ready to integrate into `main` within its defined subset.** No blocking correctness issue was reproduced. The evidence supports lazy application, selective lexical capture, one-entry shared thunk evaluation, original-anchor WHNF updates, recursive scopes, demand-based blackholes, first-class non-strict `seq`, snapshot isolation and deterministic observation/batch behavior. The existing CBV behavior remains covered and was independently sampled.

The two Low findings concern documentation and test infrastructure, with explicit follow-up criteria and independent evidence limiting their effect on this decision. Static name/structure validation, runtime correctness of the supported subset and scientific experimental validity remain separate claims. B05 supplies the runtime foundation for the next milestones without claiming that those later features or measurements are already complete.
