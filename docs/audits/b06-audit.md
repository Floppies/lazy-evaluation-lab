# B06 Audit: Lists, Pattern Matching, and Recursion

Date: 2026-11-10. Formal milestone audit: **B06.12**.

## 1. Executive Summary and Verdict

**ACCEPTED WITH LIMITATIONS.** The supported B06 Core CBV/CBNeed implementation is ready for integration into `main`. No reproducible production correctness defect or blocking semantic conflict was found. Two **Low / Confirmed / Open** findings concern current implementation-status prose and the inherited structural fingerprint helper. Neither blocks integration; section 8 gives evidence and closure criteria.

The complete suite passed **1,960 tests, zero failures**, both normally and under branch coverage. Overall coverage is **95.50% of executable lines / 88.46% of branch outcomes**; engine plus runtime is **93.06% / 82.55%**. These percentages are separate measurements, not pytest-cov's combined percentage. No coverage threshold was invented.

Acceptance also rests on reviewing the branch diff, operational continuations and test assertions, plus independent bounded probes. Those probes checked demand/error boundaries, ordered folds, mutual recursion, sharing, 375 individual session transitions, 15 retained snapshots, batch/trace equivalence, exact evaluator budgets, cyclic values and deep traversal. This is evidence for the supported interpreter subset, not a proof of arbitrary executions, equivalence to GHC, or experimental validity.

Only this report was added. No production code, existing tests, specifications, ADRs, milestones, workbook or historical audits were edited. No permanent tests or dependencies were added; no commit, branch change or pull request was made.

## 2. Audited Revision, Environment and Methodology

### Revision and supplied state

| Item | Audited value |
| --- | --- |
| Branch | `feature/lists-and-recursion` |
| HEAD | `5d35885555c0b0ab4f82136f52ec670f6b2529de` |
| Local `main` and merge base | `23b6d462f547c377d565d37ffb5761780802a705` |
| Initial working tree | Clean; no local modifications included |
| Committed B06 diff | 25 files; 4,860 insertions, 92 deletions |
| Interpreter | Repository `.venv/Scripts/python.exe` |
| Python / OS | Python 3.14.3, MSC v.1944 AMD64; Windows 11 build 26200 |
| Installed tooling | pytest 9.1.1; pytest-cov 7.1.0; coverage.py 7.16.2 |

The review used the supplied checkout and local merge base, without fetching or substituting another revision. Change size is context, not a quality metric. Shared engine paths, the rewritten session coordinator, new runtime representations and changes to existing tests were reviewed. Existing assertions were not removed by the B06 test changes inspected here.

The planning table currently marks B06.1–B06.10 Completed, B06.11 In Progress and B06.12 Pending. Those administrative states were preserved. This report assesses the implemented B06.11 behavior and supplies the B06.12 decision; it does not silently close planning entries.

### Authority

Sources were [AGENTS.md](../../AGENTS.md), [Core evaluation contract](../core-evaluation-contract.md), particularly sections 13–16, [technical specification](../specifications/technical-specification.md), [language specification](../specifications/language-specification.md), [milestones](../planning/milestones.md), `docs/planning/gantt.xlsx`, ADR-001/002/005/006/007, and the [B04](b04-audit.md) and [B05](b05-audit.md) audits. Core/runtime module documentation and the shared capture/free-variable boundary were also checked.

The Gantt was read through ZIP/XML. Worksheet `Gantt B`, rows 18 and 41, assigns B06 constructors, `case`, mutual recursion, `map`/`take`/folds and infinite lists, after B05, with 20 planned hours. It does not contain separate acceptance cells for each subtask; milestones and operational contracts supply the detail.

Technical specification section 16.1 gives its accepted v2.0 revisions precedence over retained v1.1 descriptions. Consequently, equation-based source matching, ordinary optional `main`, mutually recursive local `let`, name-based lexical environments, on-demand globals and first-class curried `seq` govern this review. Section 12's source `case` programs are algorithmic references expressed through supported equations in the tests. They do not require adding source `case` syntax. The explicit current constructor/default policy is in evaluation-contract section 16. Historical ADR open-question lists and stage-specific prose do not overturn those rules. No unresolved normative contradiction requiring a new design decision was identified; current-status drift is recorded separately in F01.

### Verification method

Review followed evaluation, reference return, explicit forcing, continuation consumption, environment restoration and canonical traversal. Assertions were examined for their ability to reject plausible wrong behavior, rather than accepting green tests as sufficient evidence.

Independent probes ran through Python stdin using the repository interpreter. They were temporary, outside the coverage measurement, and added no files or tests. An iterative graph digest encoded dataclass fields, heap cells/capacities/counters, frames, mappings and encounter-index backreferences while retaining visited objects. Additional checks used object identity directly, including the designated global ancestor and original heap-cell/payload preservation. These checks did not depend exclusively on `runtime_fingerprint()` or recursive dataclass equality. Python's recursion limit was not changed.

Expected language errors and deliberately forged states used to test the fingerprint were distinguished from evaluator defects. Every recursive or potentially nonterminating evaluator probe had an explicit evaluator budget and a bounded harness loop.

## 3. Scope and Contract Compliance

Implementation paths below are relative to `src/lazy_lab/`; test paths are relative to `tests/`.

| Subtask | Contract assessment and implementation | Principal evidence |
| --- | --- | --- |
| B06.1 — contract | Section 16 defines arities, strategy-specific field demand, ordered matching, defaults, canonical DFS, occurrence counting and limits. ADR-001/002/005/006/007 remain compatible. | Contract-to-code review; no semantic change proposed. |
| B06.2 — representation | `runtime/constructors.py:23,66`: immutable `ConstructorValue(tag, fields)`; `Nil` arity 0, `Cons` arity 2; exactly `1 + arity` slots; original references retained. | `runtime/test_constructors.py`; independent live-reference/capacity checks. |
| B06.3 — lazy constructors | `engine/core_machine.py:274,840`: fields receive ordinary CBNeed thunks; constructor WHNF and its forcing leave fields deferred. | `integration/test_cbneed_constructors.py`; sharing and `seq` probes. |
| B06.4 — strict constructors | `core_machine.py:2001`: each field is evaluated then explicitly forced, left to right, before allocation. | `integration/test_cbv_constructors.py`; competing-error probe. |
| B06.5 — case | `core_machine.py:257,2081`: explicit scrutinee demand, ordered selection, branch environment and restoration; field/original-default references preserved. | `integration/test_core_case.py`, including direct identity assertions. |
| B06.6 — errors/edges | Unmatched constructors and incompatible non-list scrutinees without a default raise `PatternMatchError`; defaults accept any WHNF. | Non-exhaustive/default tests; six independent failed-checkpoint checks. |
| B06.7 — WHNF observation | `runtime/observation.py:93`: passive `ConstructorWHNF(tag, arity)`, with no field traversal or internal references. | Runtime observation tests; result-consumer/ASK tests. |
| B06.8 — materialization | `runtime/materialization.py:52`; `engine/result_consumer.py:353–640`; session coordination: iterative DFS, evaluator bridge, complete/partial canonical trees and separate budgets. | Materialization runtime/integration modules; exact-boundary and deep probes. |
| B06.9 — list operations | `map`, `take`, descending `range` and their compositions remain mini-language programs. No Python primitive dispatch was added for them. | `integration/test_recursive_list_operations.py`; both strategies and lazy poison avoidance. |
| B06.10 — folds | `foldr`, `foldl`, `foldlStrict` remain source definitions; `seq` demands each strict intermediate accumulator to WHNF. | `integration/test_fold_operations.py`; independent subtraction folds distinguish association/order. |
| B06.11 — infinite lists | CBNeed `from` is productive for finite prefixes; CBV stops at its evaluator budget; partial infinite results obey node limits and batch accounting. | `integration/test_infinite_list_operations.py`; independent `from` and cyclic `ones` checks. |

No later-milestone primitive, instrumentation, STG, CBN or GC requirement was used as an acceptance condition.

## 4. Semantic Correctness Findings

### Constructors, references and demand

Constructor objects have no extra identity anchor. Under CBNeed, each deferred field uses ADR-007's separate immutable payload and stable one-slot anchor; capturing a local reference does not demand it. Forcing a constructor returns its existing reference without traversing fields. Common thunk updates resolve WHNF and replace the original anchor without changing capacity. Under CBV, `ConstructorFieldsFrame` keeps the original environment and field order; the final constructor is allocated only after both field demands complete.

Runtime tests verify tag/arity errors and allocation atomicity. Existing integration tests inspect deferred payload captures and verify that a field anchor and its referenced global eventually target the same constructor. Independent transition checks verified allocated field references, constructor capacities, live thunk payloads, active update frames and unchanged previous cells. No invalid reference emitted by the evaluator was found. This does not certify arbitrary manually forged heap graphs at an external API boundary.

### Matching, lexical scope and recursion

`CoreCaseFrame` records the reference returned by scrutinee evaluation before forcing it. Constructor binders receive the exact stored field references; default binders receive that original scrutinee reference, including when forcing resolves it to a different reference. Alternatives are scanned in order, including a default before a constructor. `RestoreEnvironmentFrame` prevents branch bindings from leaking; escaping closures selectively capture their branch-local references.

The direct tests inspect selected alternatives and use `is` for field bindings and environment restoration. End-to-end tests cover `Nil`, `Cons`, non-list fallback, non-exhaustive cases, nested cases and returned closures. A leading source variable equation still avoids an unnecessary `CoreCase`; no lowering change was introduced in B06.

Independent mathematical/scope probes supplied **12 successful executions**, six under each strategy:

| Program | Observed result |
| --- | --- |
| `foldr sub 0 [1,2,3]`, where `sub a b = a - b` | `2` |
| `foldl sub 0 [1,2,3]` | `-6` |
| `foldlStrict sub 0 [1,2,3]` | `-6` |
| Mutually recursive global even/odd list traversals on four elements | `True` |
| Mutually recursive local traversal helpers, including forward local references | `True` |
| A closure returned from a `Cons` branch and called with an outer `h = 99` | Captured head `7` |

For reproducibility, the local recursion source was:

```haskell
done [] = True
done (h:t) = False
tail (h:t) = t
main = let { even xs = e xs; odd xs = o xs; e xs = if done xs then True else odd (tail xs); o xs = if done xs then False else even (tail xs) } in even [1,2,3,4]
```

The escaping closure source was `choose [] = \x -> 0`, `choose (h:t) = \x -> h`, followed by `main = let { h = 99; f = choose [7] } in f 0`, with newline-separated definitions. All 12 runs completed with an empty stack and local environment restored to the designated global object. Their configuration was complete materialization, 3,000 evaluator steps, 100 result nodes and a session batch of 10,000 transitions.

Local initialization now accepts `EVALUATION` and `RESULT_MATERIALIZATION` (`core_machine.py:701`). This admits generated parameter aliases and source `let` groups encountered while forcing lazy result fields. The existing recursive-map test explicitly checks local-installation transitions in the latter phase. Reservation, source-order CBV initialization, unused CBNeed bindings and shared updates retain their B04/B05 rules; no new recursive initialization policy was introduced.

### Folds and `seq`

Existing poison-value tests distinguish lazy `foldr` short-circuiting, lazy `foldl` discarding an intermediate accumulator, and `foldlStrict` demanding it. A poisoned list spine also distinguishes `foldr` from both left folds. Thus the evidence goes beyond equal sums, which alone cannot establish fold order or strictness.

An independent CBNeed run of `loop = loop; main = seq (loop : loop) 7` (newline-separated definitions) returned `7` while the `loop` global remained `PendingThunk`. This verifies that accumulator forcing to constructor WHNF is not recursive field materialization. It does not claim a constant-space bound for strict folds: allocation attribution and reclamation remain later work.

No confirmed production defect was found in these areas.

## 5. Materialization, Demand and Budget Analysis

### Traversal and partial trees

WHNF observation is passive. Complete materialization visits constructor fields depth-first, left to right. `advance_materialization` observes already-resolved nodes; unresolved references set `awaiting_whnf`. A separate administrative request installs `Force` plus `MaterializationDemandFrame`; evaluator transitions execute the computation and resume the saved traversal at the root. These evaluator transitions retain `RESULT_MATERIALIZATION` and consume the evaluator budget.

Every canonical occurrence counts, including repeated references to a shared constructor. Canonical output contains values/tags/partial placeholders, not heap references. A visited constructor with unfinished children is represented by `CanonicalPartialConstructor`; `CanonicalPending` represents the next unvisited occurrence and `unvisited_fields` records remaining siblings. Complete children remain attached when traversal stops. Completion publishes the existing completed tree rather than traversing it again.

`Cons` tail validation occurs when that tail is visited as a list, after resolving its WHNF if necessary. Node-limit checking precedes inspection/forcing of the next field. For **both strategies**, independent `main = 1 : 2` runs with node limits 1 and 2 produced partial `RESULT_LIMIT_REACHED` results; limit 3 reached the tail and raised the expected `TypeError`. `main = [1,2]` completed at its exact five-node limit under both strategies. These are eight successful runs and two expected errors, not failed tests.

The competing-error source `main = [[1 + True]] : (if 0 then [] else [])` raised the inner integer-operand error first under both strategies, rather than the outer tail's condition error. A direct deep DFS over 2,000 allocated `Cons` cells completed at exactly **4,001 canonical occurrences**, checked iteratively without equality/repr of the deep tree.

### Limit categories and exact boundaries

| Boundary | Observed behavior |
| --- | --- |
| `BATCH_LIMIT` | Current session used its total transition capacity; execution/progress remain resumable. Evaluator and consumer transitions both use this capacity. |
| `EVALUATOR_BUDGET` | Evaluator cannot advance. Before result materialization, the machine remains `RUNNING`, with no fabricated canonical result. This preserves B04/B05's API. |
| `STEP_LIMIT_REACHED` | During materialization, the consumer publishes a partial result when WHNF demand needs unavailable evaluator work, including an interrupted field computation. |
| `RESULT_LIMIT_REACHED` | The next canonical occurrence would exceed the result budget; saved partial structure is published without demanding it. |

Independent exact-budget probes used `main = (1 + 2) : []` under CBNeed. Root WHNF requires **10 evaluator transitions** and complete materialization **31**. Each budget below was compared with session sizes 500 and 1, including identical concatenated traces, statuses, counters and partial results:

| Evaluator limit | Stop reason / status | Visited canonical nodes |
| --- | --- | --- |
| 1, 9 | `EVALUATOR_BUDGET` / `RUNNING` | Materialization not started |
| 10, 11 | `TERMINAL_STATUS` / `STEP_LIMIT_REACHED` | 1 |
| 30 | `TERMINAL_STATUS` / `STEP_LIMIT_REACHED` | 2 |
| 31 | `TERMINAL_STATUS` / `COMPLETED` | 3 |

Under CBV, `main = [1,2]` completed materialization at its exact **26-evaluator-transition** budget, even with session batches of one. Already-WHNF fields require only administrative DFS work; budget exhaustion alone must not prevent that work. Existing tests also cover selection under `ASK_AT_WHNF`, exhausted budgets before and during demand, terminal idempotence and invalid tails hidden by a node limit.

Before root WHNF, CBV infinite-source tests deliberately return `EVALUATOR_BUDGET` with `RUNNING`, not `STEP_LIMIT_REACHED`. Conflating these categories would break the existing API. Terminal limit snapshots preserve their traversal/runtime state for inspection; this audit does not promise resuming a terminal status merely by increasing a limit.

## 6. Regression, Determinism and Snapshot Verification

The diff adds constructor/case WHNF recognition and continuations, extends the local-initialization phase guard and integrates constructor materialization. It does not replace CBV application/global activation, CBNeed thunk lifecycle, lexical capture or first-class predefined dispatch. All existing B04/B05 regression tests remain in the passing complete suite.

Independent single-transition verification used these four CBNeed workloads, with 3,000 evaluator steps, FULL tracing, complete materialization, and result-node limits 100 for the first two and 7 for the last two:

| Newline-separated source | All transitions | Evaluator transitions | Visited nodes / outcome |
| --- | --- | --- | --- |
| `main = [[1+2], [4]]` | 94 | 67 | 9 / Completed |
| `xs = [1+2]`; `main = [xs,xs]` | 94 | 67 | 9 / Completed |
| `ones = 1 : ones`; `main = ones` | 62 | 40 | 7 / Result limit |
| `from n = n : from (n+1)`; `main = from 1` | 125 | 103 | 7 / Result limit |

The runs checked **375 individual transitions**, including **31 WHNF thunk updates**. Previous heap cells were checked by identity, previous stack frames retained, allocation capacities preserved, total slots recomputed, and live constructor/payload references inspected. Each active evaluating thunk had its original-anchor update frame. Every active local environment reached its designated global ancestor by identity. Consumer transitions changed neither simulated heap cells nor evaluator counts. An iterative digest was checked again for **15 retained historical snapshots** after subsequent execution.

For each workload, one-step execution matched an uninterrupted batch of 10,000 transitions in full graph digest and concatenated trace. **16 additional configurations** checked batch sizes 2 and 7 with FULL tracing, and size 3 with EVENTS and METRICS_ONLY. EVENTS retained the same operational trace; METRICS_ONLY retained none, while final machine state and accounting remained equivalent. Shared `xs` counts twice in the canonical tree; productive cyclic `ones` hits its result budget rather than falsely detecting a blackhole.

Independent failure-atomicity checks stepped to six actual B06 errors: unmatched `Nil`/`Cons` cases and a materialized boolean tail, under each strategy. The failed input checkpoint retained its control, result progress, counters, stack and exact heap-cell objects. Errors remained explicit Python exceptions, consistent with the inherited controller boundary, rather than invented `RUNTIME_ERROR` successor states.

Finally, a validated Core expression constructed iteratively as 2,000 nested `CoreCase(previous, (CoreDefaultAlt("v", CoreVar("v")),))` wrappers around `CoreInt(7)` completed under both strategies. Each required **14,003 evaluator transitions**, with a 30,000-step budget; execution was interrupted after 50 session transitions and then resumed. Both returned `7`, restored the global environment and emptied the stack while preserving the interrupted snapshot. This tests operational depth independently of parser nesting limits and the recursive fingerprint.

## 7. Test Results and Coverage

Commands ran from the repository root with installed dependencies. `-p no:cacheprovider` avoided a local pytest-cache write warning; it does not exclude tests.

| Command using `.venv/Scripts/python.exe` | Actual outcome |
| --- | --- |
| `-m pytest tests/runtime tests/integration tests/engine -q` | Initial path-discovery mistake: `tests/engine` does not exist; exit 1, no tests ran. A cache-path warning was also emitted. Corrected immediately below. |
| `-m pytest tests/runtime tests/integration -q -p no:cacheprovider` | **635 passed**, 1.10 s |
| `-m pytest -q -p no:cacheprovider --cov=lazy_lab --cov-branch --cov-report=term-missing --cov-report=json:.coverage-b06.json` | **1,960 passed**, 4.76 s |
| `-m pytest -q -p no:cacheprovider` | **1,960 passed**, 4.02 s |
| `-m pytest tests/ast tests/frontend tests/core -q -p no:cacheprovider` | **1,020 passed**, 1.11 s |

These runs overlap; their counts must not be added as distinct tests. No failing test, skip or expected-failure result was reported in the successful runs. Temporary probe-harness corrections were not production defects or pytest results; all independent outcomes cited above were actually obtained.

Coverage denominators were extracted from the fresh JSON export. Branch percentage is covered branch outcomes divided by all measured branch outcomes; combined percentage uses lines plus branch outcomes.

| Scope | Lines covered / total | Line coverage | Branches covered / total | Branch coverage | Combined |
| --- | --- | --- | --- | --- | --- |
| Entire `lazy_lab` | 2,865 / 3,000 | 95.50% | 1,065 / 1,204 | 88.46% | 93.48% |
| Engine + runtime | 1,569 / 1,686 | 93.06% | 563 / 682 | 82.55% | 90.03% |
| Nine B06-touched production modules | 1,247 / 1,356 | 91.96% | 484 / 596 | 81.21% | 88.68% |

The last scope comprises all three engine modules plus runtime `constructors`, `materialization`, `observation`, `stack`, `state` and `transitions`. It measures whole modules, including inherited code; it is not changed-line coverage.

Relevant remaining gaps include defensive wrong-type/arity/state/phase checks and unsupported-strategy paths. In particular, the suite leaves 9 lines/9 branch outcomes uncovered in `runtime/materialization.py`, including repeated/inconsistent traversal misuse; 3/3 in `constructors.py`; and 19/19 in `engine/result_consumer.py`. `session_runner.py` misses lines 43, 60, 71 and 122, including the batch-capacity check following a materialization evaluator-budget stop. Core-machine coverage is 560/631 lines and 300/374 branch outcomes; many gaps reject inconsistent continuation/configuration states. These gaps were reviewed, not declared covered by successful neighboring paths. Independent probes were intentionally excluded from these coverage totals.

The existing tests contain meaningful identity, phase, budget, payload and poison-demand assertions. Their remaining fingerprint limitation is F02. No critical missing regression requiring a permanent audit test was identified. No minimum coverage or broad randomized test matrix was imposed.

## 8. Findings, Limitations and Risks

### F01 — Current status prose still defers implemented constructors and matching

- **Classification:** Documentation/diagnostic wording, not a production semantic defect.
- **Severity:** Low. **Status:** Confirmed / Open. **Blocks integration:** No.
- **Location:** `docs/core-evaluation-contract.md:5`; `docs/core-ir.md:7,198`; `docs/decisions/ADR-005-lexical-runtime-environments.md:3,83`. Related stale wording appears in `engine/result_consumer.py:313,316`.
- **Evidence / reproduction:** Search the named documents for `constructors/case`, `constructor matching` and `remain deferred`. They still describe executable constructors or matching as pending. Fresh constructor/case/materialization tests and section 16 establish the implemented behavior. Calling the intentionally atomic-only `consume_materialized_result` directly on a constructor raises a message saying complete constructor materialization is not implemented, although `start_constructor_materialization` and the session runner implement it.
- **Affected contract:** Documentation authority and current implementation-status accuracy under AGENTS.md; evaluation-contract section 16. The atomic helper's rejection is valid; its explanation is outdated.
- **Impact:** Readers may confuse a helper-specific boundary or stale overview with missing B06 behavior. No wrong result or demand change was reproduced.
- **Minimal correction / closure:** In a separately authorized documentation patch, update current scope/status sentences and direct atomic-helper callers to the constructor consumer. Preserve historical stage descriptions, B04/B05 evidence and deferred CBN status. No semantic ADR change is required.
- **Provenance:** Similar category to B04/B05 documentation findings, but this is B06 constructor-status drift. The prior CBNeed status corrections already present in the merge base are not being reported as newly broken semantics.

### F02 — Inherited fingerprint omits designated identity and recurses on deep trees

- **Classification:** Test-infrastructure/evidence limitation; inherited from **B05 F02**, not introduced by B06.
- **Severity:** Low. **Status:** Confirmed / Open. **Blocks integration:** No.
- **Location:** `tests/helpers/runtime_equivalence.py:12,47,61`; used by `tests/integration/test_materialization_session.py:113` and `test_infinite_list_operations.py:215`. Relevant production boundary: `runtime/captures.py:41`.
- **Evidence / reproduction:** Create a ready-to-evaluate `CoreLam("x", CoreVar("y"))` state whose local environment extends its global environment with immediate `y = 7`. Replace only the designated global environment with `Environment(g.bindings, g.parent)`, retaining the original local parent. The two states have equal fingerprints. Stepping the original succeeds; stepping the deliberately inconsistent copy raises `ValueError: Global environment is not an ancestor of the definition environment`. Separately, wrap `CoreInt(0)` in 2,000 `CoreLam("x", previous)` nodes and fingerprint it: **RecursionError**. Both limitations were reproduced freshly.
- **Affected contract:** ADR-005/007 lexical identity and snapshot/determinism evidence; AGENTS.md's deep-traversal verification rule. The forged graph is a sensitivity test, not evidence that production emits it.
- **Impact:** Equal fingerprints alone cannot certify the global-boundary identity relationship or arbitrary-depth equivalence. This matters because B06 adds more fingerprint-based batch comparisons.
- **Minimal correction / closure:** Add explicit designated-global ancestry checks to equivalence tests, or encode that relationship with normalized graph identities; make deep normalization iterative. Retain sensitivity tests when changing the helper. Existing direct identity assertions and this audit's independent graph/ancestry checks support acceptance meanwhile.

**Finding totals: Critical 0; High 0; Medium 0; Low 2.** Both are confirmed, nonblocking and open. One concerns B06 documentation and one is inherited test tooling. No production defect is confirmed or suspected strongly enough to report as a separate finding; none was fixed during this audit.

### Evidence limitations and future capabilities

| Boundary | Practical limitation / follow-up |
| --- | --- |
| Trusted internal state construction | Reference checks here cover evaluator-produced states, not arbitrary external graphs or mutable extension objects. External API validation remains an inherited integration obligation. |
| Coverage and finite probes | Defensive branches remain unexecuted; bounded examples and static validation are not proofs of every runtime path. Host-level dataclass equality/repr/hash still have deep-tree limits. |
| Error boundary | Runtime/type/pattern errors generally propagate as Python exceptions. A controller must deliberately map them without mutating the failed checkpoint or conflating errors with limits. |
| B07 instrumentation | Raw transition/slot counts include generated aliases and anchor/payload overhead. They are operational budget evidence, not comparable source-level metrics or experimentally validated speed/space claims. |
| B08 replay | Compact traces and immutable snapshots do not establish persisted replay or an interactive visualizer. |
| B09–B11 | STG lowering/execution and nonmemoizing CBN remain outside this verdict. Same Core compatibility is an architectural property, not executed three-strategy equivalence. |
| B12–B13 | No reclamation/lifetime certification. Payloads and other unreachable objects remain allocated; copying heap/stack storage and repeated analysis can have substantial host costs. |
| B14–B16 | No experimental campaign, benchmark calibration or equivalence with external C/Haskell runtimes was audited. |

These future capabilities are not blocking B06 defects.

## 9. Recommendations and Closure Criteria

1. Integrate the recorded B06 implementation after normal review. There is no reproduced blocking production fix required by this audit.
2. Track F01 and inherited F02 with the explicit nonblocking closure criteria above. Update current implementation-status documentation without rewriting historical audits or changing accepted semantics.
3. Reconcile B06.11/B06.12 administrative states after accepting the report. This audit deliberately leaves `milestones.md` and the Gantt untouched.
4. Preserve separate evaluator/result-consumer accounting, original pattern references, stable update anchors and DFS progress in subsequent work. Before using operational costs experimentally, complete B07 attribution and budget/category definitions at the controller boundary.
5. If production or normative contracts change before merge, rerun the affected focused tests, complete suite, branch coverage and relevant independent boundary probes. This verdict applies to the recorded local revision, not an unreviewed later commit or remote `main`.

No specification or semantic ADR revision is needed to accept the observed implementation. Only the current-status corrections in F01 are recommended. The audit neither resolves a new design question nor implements any future capability.

## 10. Merge Readiness Conclusion

**ACCEPTED WITH LIMITATIONS — B06 is ready for integration into `main` within its defined CBV/CBNeed subset.** The evidence supports constructors, ordered matching, lexical pattern bindings, direct/mutual list recursion, strategy-dependent demand, first-class `seq`, complete/partial canonical materialization, bounded infinite/cyclic values and deterministic batching without losing B04/B05 guarantees. No blocking production defect was reproduced.

The two Low findings remain explicit follow-ups. Static compilation/validation, runtime correctness evidence and experimental validity are separate claims; this report certifies neither later milestones nor scientific metric comparability.

Audit artifact ownership: **created `docs/audits/b06-audit.md` only**. The temporary coverage JSON export was removed after extracting its totals; `.coverage` is an ignored measurement artifact. No probe source, new test, dependency, production/specification/ADR/planning edit, commit or branch change is part of this audit.
