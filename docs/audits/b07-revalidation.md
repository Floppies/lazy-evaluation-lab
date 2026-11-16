# B07 Findings Revalidation: Instrumentation and Metrics

Date: 2026-11-16. Task: **B07.11.4d — Findings Revalidation**.

## 1. Executive Summary and Decision

**ACCEPTED WITH LIMITATIONS.** F01 and F02 are **CLOSED**: the original deep comparison and complete/partial JSON export failures no longer reproduce, their corrected implementation was inspected, and focused, full-suite and independent structural checks pass. No new blocking production defect was found. **Integration of B07 into main is recommended.**

F03 is **PARTIALLY RESOLVED**. All 11 original source/test whitespace violations were removed, but the complete branch still fails whitespace validation because the subsequently committed historical audit has one extra blank line at EOF. This is a **Low, nonblocking** residual issue. The historical report was preserved exactly as requested; this revalidation does not declare the branch whitespace-clean.

| Finding | Original severity | Revalidation status | Integration impact |
| --- | --- | --- | --- |
| F01 — Deep canonical comparison | Medium | **CLOSED** | Original blocker removed |
| F02 — Deep complete/partial JSON export | Medium | **CLOSED** | Original blocker removed |
| F03 — Branch whitespace | Low | **PARTIALLY RESOLVED** | One nonblocking documentation violation remains |

The focused suite passed **57 tests**. The complete suite passed **2,080 tests**, both normally and under branch coverage. Fresh overall coverage is **95.15% of executable lines / 87.00% of branch outcomes**. Independent probes verified deep result structure and JSON syntax using Node.js's independent parser, rather than counting tag substrings.

This is a focused follow-up to [the original audit](b07-audit.md), whose historical FIXES NEEDED conclusion remains unchanged. Its broader operational evidence is retained as the baseline, not represented as a newly repeated audit. Only this revalidation report was created; no production, test, contract, specification, ADR, planning, dependency or historical-audit file was edited.

## 2. Revalidated Revision and Environment

### Actual checkout

| Item | Observed value |
| --- | --- |
| Repository / branch | Floppies/lazy-evaluation-lab / `feature/metrics` |
| Original audited commit | `54e787b0c568f0c916f0198f9ab5b4ed99cf0982` |
| Revalidated HEAD | `389795ace3c4672e1a5c22e1a0f29fbf8a337e36` |
| Local main and merge base | `34363572aa356b99ca048982f8f1d0145aa3b009` |
| Initial working tree / index | Clean; no local modifications or untracked files |
| Post-audit diff | 12 files; 838 insertions, 89 deletions, including the 494-line original audit |
| Python | Repository `.venv/Scripts/python.exe`; 3.14.3, MSC v.1944, AMD64 |
| OS | Windows 11, build 26200 |
| Installed tools | pytest 9.1.1; pytest-cov 7.1.0; coverage.py 7.16.2 |
| Independent JSON verifier | Existing `C:\Program Files\nodejs\node.exe`, Node.js **v22.20.0** |
| Python recursion limit during probes | **1,000**, unchanged |

No fetch, branch change or dependency installation was performed. The effective checkout, not a presumed remote revision, was revalidated.

The post-audit commits inspected were:

| Commit | Relevant change |
| --- | --- |
| `037cca5` | Adds the original B07 audit |
| `f847436` | Iterative canonical comparison and opaque scan; two regression tests |
| `80ea1c0` | Iterative canonical conversion and JSON encoding; three regression tests |
| `389795a` | Original source/test whitespace cleanup |

Commands used to establish the revision and change boundary included `git status --porcelain=v1`, `git branch --show-current`, `git rev-parse HEAD`, `git rev-parse main`, `git merge-base HEAD main`, `git log --oneline 54e787b0c568f0c916f0198f9ab5b4ed99cf0982..HEAD`, and `git diff --stat` / `--numstat` / file-specific diffs between the audited commit and HEAD.

AGENTS.md, the original findings/closure criteria and Appendix A, and metrics-contract sections 7–8 were reviewed. Existing evaluation/instrumentation semantics remain the baseline. Post-audit changes to evaluator/runtime/reducer files are whitespace only; the operational 1,206-transition matrix was therefore not repeated. Existing test assertions were not weakened: the substantive test changes add two comparison and three export tests.

The SHA-256 of `docs/audits/b07-audit.md` was recorded before verification and checked again at completion:

~~~text
1487C5158CA44B745A018563D17322BBFE00AE7C8004027B5DE7886F1BABC562
~~~

### Original reproducer execution

The original Appendix A was executed directly from the unchanged report, avoiding a substitute shallow example:

~~~powershell
.venv/Scripts/python.exe -c "from pathlib import Path; s=Path('docs/audits/b07-audit.md').read_text(encoding='utf-8'); code=s.split('~~~python',1)[1].split('~~~',1)[0]; exec(compile(code,'b07-audit.md:Appendix A','exec'))"
~~~

Actual output, exit **0**:

~~~text
left COMPLETED 63638 56435 2401 1000
right COMPLETED 63638 56435 2401 1000
comparison OK
dict OK
json OK
csv OK
partial RESULT_LIMIT_REACHED 14426 7222 2401 1201
partial dict OK
partial json OK
~~~

These are the original workloads and budgets: two independent 1,200-element finite runs, each limited to 150,000 evaluator transitions and 3,000 result nodes, and cyclic output limited to 30,000 evaluator transitions and 2,401 result nodes. No depth restriction or recursion-limit adjustment was introduced.

## 3. F01 — Evidence and Closure Decision

**Decision: CLOSED.**

### Corrected implementation

- `src/lazy_lab/metrics/comparison.py:166`: _contains_opaque_function uses a pending list and while loop. It does not call itself.
- `comparison.py:187`: _canonical_values_equal uses a stack of node pairs. It compares exact canonical classes, scalar values, constructor tags, field counts/order, ConstructorWHNF arity, and partial-constructor unvisited_fields.
- `comparison.py:377`: assess_comparability checks both trees for opaque functions before calling the iterative comparator. No recursive dataclass equality is used on the result trees.
- `comparison.py:239` and `301`: complete-cost ratios, applicable metrics, completeness, effective policy and declared-factor rules remain intact in the reviewed diff.

OpaqueFunction equality inside the private comparator is not a public claim of functional equivalence: the public assessment excludes any opaque-containing result from structural checking first. This preserves the active contract's existing whole-result exclusion. Partial measurements still fail the completion requirement rather than being reported as complete costs or false semantic mismatches.

### Executed evidence

| Check | Actual outcome |
| --- | --- |
| Original two independent deep completed runtime results | Assessment returns normally; both runs remain COMPLETED with 2,401 nodes |
| Deep equal reconstruction, independent root and tail objects | Comparable |
| Difference at the last list element, 1,199 tail edges below the root | Exactly `different_observable_result` |
| Valid deep list with an OpaqueFunction at that last head | Opaque detected iteratively; public assessment preserves structural-check exclusion |
| Deep non-opaque list | Opaque scan returns false |
| compare_metric on deep equal results | evaluator_transitions **56,435 / 56,435**, delta **0**, ratio **1.0** |
| Twelve type/value/tag/arity/field/partial-metadata distinction pairs | Every unequal pair rejected; corresponding reflexive checks pass |
| Existing comparison/ratio/truncation regressions | Pass in focused and full suites |

The original pair consists of genuinely separate evaluator executions. The additional difference and opaque cases are explicitly constructed valid canonical variants attached to the completed measurement for comparison testing; they are not claimed to be additional mini-language executions. The equal variant was rebuilt iteratively with independent constructor and integer objects. The changed last head was CanonicalInteger(-123), and the opaque variant used OpaqueFunction at the same position with a proper Nil tail.

The 12 distinction pairs cover Integer versus Boolean, different integer/boolean values, WHNF arity/tag, complete-constructor tag/field count, partial tag/field count/child value/unvisited_fields, and complete versus partial canonical classes. They supplement the new tests at `tests/metrics/test_comparison.py:439` and `467`.

The original failure is resolved without a relevant reproduced comparison regression. No API, contract or ADR change is needed for closure.

## 4. F02 — Evidence and Closure Decision

**Decision: CLOSED.**

### Both corrected levels

`src/lazy_lab/metrics/export.py:114` converts canonical results using an explicit stack of source/target/index tasks. Child positions are preserved, and partial nodes retain unvisited_fields. It does not recurse over canonical children.

`export.py:188` encodes dict/list containers with explicit value/text tasks and StringIO. Keys are sorted; commas, brackets and braces are scheduled explicitly. json.dumps remains at `216` and `235` for keys/scalars, not for recursively walking the generated dict/list tree. `export.py:286` routes the public exporter through this encoder.

JSON is now compact instead of pretty-printed. The contract promises deterministic schema-v1 data rather than a particular indentation style; configuration, canonical kind tags, status, stop reason and measurement fields are unchanged. The CSV implementation is unchanged.

### Deep syntax, structure and passivity verification

A separate bounded stdin probe evaluated one finite and one partial workload with the same budgets as Appendix A, then validated both conversion and final text. Results:

| Measurement | Finite list | Bounded cyclic partial result |
| --- | ---: | ---: |
| Status | COMPLETED | RESULT_LIMIT_REACHED |
| Total transitions | 63,638 | 14,426 |
| Evaluator transitions | 56,435 | 7,222 |
| Counted result nodes | 2,401 | 2,401 |
| JSON characters in this probe | 94,827 | 127,158 |
| Structural preorder records | 2,401 | 2,402 |
| Canonical variants | 1,201 constructors; 1,200 integers | 1,201 partial constructors; 1,200 integers; 1 pending placeholder |

The character counts use workload IDs `finite` / `partial` and session IDs `finite-validation` / `partial-validation`; they are not schema requirements.

Verification did more than count Cons tags:

1. Canonical input was converted independently to a flat preorder sequence using an explicit Python stack. Constructor entries include kind, tag, field count and partial metadata; leaf entries include kind and value.
2. run_record_to_dict's tree was independently traversed into the same sequence.
3. Final JSON text was passed through stdin to existing Node.js and parsed with **JSON.parse**. This validates JSON grammar using a separate implementation without Python's recursive decoder limit.
4. The parsed tree was traversed iteratively in Node.js. Exact schema keys and variant fields were checked, then its flat records and top-level metadata were returned as shallow JSON and compared against the Python expectations.
5. Finite integer values were checked against **1,200 down to 1**, with a final Nil leaf. Partial integer values were all **1**; its last partial Cons had one Pending child and **unvisited_fields = 1**, while preceding partial constructors had **unvisited_fields = 0**.
6. The extra partial-tree preorder record is the Pending placeholder. It does not falsely increment resultNodes.
7. Every top-level measurement field, all six configuration fields, status, actual batch stop reason, all 26 primary counters and baseline were compared with the measured record/state. Schema version remained **1**.
8. Repeated serialization of each identical record was byte-for-byte deterministic. CSV counters also matched the recorded values.
9. During export, evaluator step/session evaluation and Heap.get/allocate/replace were temporarily replaced with assertion-raising functions in the probe process. Export succeeded. Transition/evaluator counts, instrumentation identity, canonical result identity, control, materialization progress, saved frames and every heap-cell identity remained unchanged.

Exact schema-key validation at the root, configuration, instrumentation and canonical variants excludes heap, stack and environment data from the exported structure. The Node verification uses only the small integer values/counters in these workloads, all within its exact numeric range; it is not being used to certify arbitrary Python integer conversion through JavaScript.

### Independent deep JSON validator

This is the Node.js validator used through `subprocess.run([node, '-e', node_code], input=text, text=True, encoding='utf-8', capture_output=True, timeout=30)`. It reads the full exported record. Its result is shallow enough for Python json.loads; no deep Python JSON decoding or recursive tree equality is involved.

~~~javascript
const assert = require('node:assert/strict');
const fs = require('node:fs');
const text = fs.readFileSync(0, 'utf8');
const d = JSON.parse(text);
function keys(x, names) {
  assert.deepEqual(Object.keys(x).sort(), names.sort());
}
keys(d, ['schema_version','workload_id','session_id','transition_index',
         'config','effective_result_policy','status','stop_reason',
         'canonical_result','instrumentation']);
keys(d.config, ['machine_kind','strategy','result_policy',
                'execution_step_limit','result_node_limit','trace_mode']);
keys(d.instrumentation, ['counters','baseline_slots']);
assert.equal(d.schema_version, 1);
const tokens = [], pending = [d.canonical_result];
while (pending.length) {
  const v = pending.pop();
  switch (v.kind) {
    case 'integer':
      keys(v, ['kind','value']);
      assert(Number.isSafeInteger(v.value));
      tokens.push(['integer',v.value]);
      break;
    case 'boolean':
      keys(v, ['kind','value']);
      assert.equal(typeof v.value, 'boolean');
      tokens.push(['boolean',v.value]);
      break;
    case 'constructor':
    case 'partial_constructor':
      keys(v, v.kind === 'constructor'
        ? ['kind','tag','fields']
        : ['kind','tag','fields','unvisited_fields']);
      assert.equal(typeof v.tag, 'string');
      assert(Array.isArray(v.fields));
      if (v.kind === 'partial_constructor')
        assert(Number.isInteger(v.unvisited_fields) && v.unvisited_fields >= 0);
      tokens.push([v.kind,v.tag,v.fields.length,
                   v.kind === 'partial_constructor' ? v.unvisited_fields : null]);
      for (let i = v.fields.length - 1; i >= 0; --i)
        pending.push(v.fields[i]);
      break;
    case 'pending':
      keys(v, ['kind']);
      tokens.push(['pending']);
      break;
    case 'opaque_function':
      keys(v, ['kind']);
      tokens.push(['opaque_function']);
      break;
    case 'constructor_whnf':
      keys(v, ['kind','tag','arity']);
      tokens.push(['constructor_whnf',v.tag,v.arity]);
      break;
    default:
      throw Error('Unknown canonical kind');
  }
}
const {canonical_result, ...metadata} = d;
process.stdout.write(JSON.stringify({tokens,metadata}));
~~~

The conversion tree, independently parsed JSON tree and original canonical tree produced identical preorder records. This comparison includes ordering, values, tags, arity and partial metadata, not only counts.

### Moderate-depth equivalence and escaping

**24 bounded payloads** were checked against:

~~~python
json.dumps(
    payload, ensure_ascii=False, sort_keys=True,
    separators=(",", ":"), allow_nan=False,
)
~~~

The new encoder's text matched exactly, and ordinary json.loads round-tripped each moderate payload. Cases included scalars, empty and mixed containers, a 2**100 integer, finite float, nested dict/list payloads through 11 wrapper levels, sorted Unicode keys, quotes, backslashes, slash, backspace/form-feed/newline/carriage-return/tab, NUL and U+001F, accented text, CJK, emoji and U+2028. Three additional payloads containing NaN / positive infinity / negative infinity raised the expected ValueErrors.

Existing JSON/CSV regressions pass. The new permanent tests at `tests/metrics/test_export.py:396,416,448` cover encoder equivalence and deep conversion/serialization. Their tag-substring assertions alone would be insufficient closure evidence; the independent syntax and full-structure checks above provide the required additional assurance.

No new production export defect was reproduced, and no schema or semantic contract change is needed.

## 5. F03 — Evidence and Closure Decision

**Decision: PARTIALLY RESOLVED. Severity remains Low and nonblocking.**

The seven source/test files listed in the original finding were inspected in the whitespace cleanup diff. All original eight trailing-whitespace and three blank-line-at-EOF violations are gone. No evaluator or instrumentation logic changed.

However, the complete committed branch still produces:

~~~text
docs/audits/b07-audit.md:494: new blank line at EOF.
~~~

| Actual command | Exit / result |
| --- | --- |
| `git diff main...HEAD --check` | **2**; one audit EOF diagnostic |
| `git diff main --check` | **2**; same single diagnostic, including the effective working-tree state |
| `git diff --check` | **0**; no local tracked patch |
| `git diff --cached --check` | **0**; no staged patch |
| `git diff main...HEAD --check -- src tests` | **0** |
| `git show 389795a --format=short --check` | **0** |

The residual violation was introduced when the audit report was added in `037cca5`; it is not an uncorrected source/test location or a semantic regression caused by the iterative fixes. It is tracked under the existing branch-whitespace finding rather than counted again as a new defect.

**Remaining closure criterion:** remove only the extra terminal blank line in the historical audit in a separately authorized whitespace-only change, without rewriting its contents or conclusions, then obtain exit 0 from both the branch-range and effective-tree whitespace checks. This task explicitly requires preserving that report, so it was left untouched. F03 cannot honestly be marked CLOSED while the requested combined-branch check fails.

## 6. Regression Tests and Coverage

Commands ran from the repository root with the existing virtual environment. No dependencies were installed.

| Actual command | Result |
| --- | --- |
| `.venv/Scripts/python.exe -m pytest tests/metrics/test_comparison.py tests/metrics/test_export.py tests/integration/test_materialization_session.py -q -p no:cacheprovider` | **57 passed**, 0.26 s |
| `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` | **2,080 passed**, 6.96 s |
| `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --cov=lazy_lab --cov-branch --cov-report=term-missing --cov-report=json:$env:TEMP/lazy-lab-b07-revalidation-389795a.json` | **2,080 passed**, 8.24 s |

All three commands exited 0, without reported failures, skips or xfails. Counts overlap and must not be added. The original Appendix A and supplemental stdin probes are separate evidence and are **not included in coverage**.

For the coverage command, PowerShell set:

~~~powershell
$env:COVERAGE_FILE = Join-Path $env:TEMP 'lazy-lab-b07-revalidation-389795a.coverage'
~~~

Fresh JSON totals were read using covered_lines/num_statements and covered_branches/num_branches, keeping the two measurements separate:

| Scope | Executable lines covered / total | Line coverage | Branch outcomes covered / total | Branch coverage |
| --- | ---: | ---: | ---: | ---: |
| Entire lazy_lab | 3,415 / 3,589 | **95.15%** | 1,225 / 1,408 | **87.00%** |
| Metrics package | 441 / 477 | **92.45%** | 137 / 178 | **76.97%** |
| comparison.py | 104 / 130 | **80.00%** | 47 / 74 | **63.51%** |
| export.py | 111 / 116 | **95.69%** | 41 / 46 | **89.13%** |
| Engine + runtime | 1,671 / 1,791 | **93.30%** | 586 / 708 | **82.77%** |

These are whole-module percentages, not changed-line coverage. The terminal's combined percentages, including its overall rounded 93%, are not branch coverage. No acceptance threshold was invented.

The larger iterative comparison implementation adds defensive/type/partial branches that the permanent suite does not fully exercise. The independent 12-pair probe exercises distinctions beyond that suite, but does not increase these measured totals. Remaining exporter gaps include invalid-input rejection. High coverage is not the basis for accepting deep syntax or structure; the independent checks supply that evidence.

Engine/runtime coverage denominators and hits match the original audit's corresponding totals. Together with the whitespace-only operational diff, this supports retaining the original runtime evidence without repeating its independent 1,206-transition matrix.

## 7. Remaining Risks and Limitations

- **One known Low issue remains:** F03's audit EOF blank line. It has no reproduced effect on evaluation, accounting, comparison or serialization.
- **No new finding was confirmed.** Both original Medium production blockers are closed. There are no newly reproduced blockers or weakened tests.
- The new deep regression tests are useful but do not permanently encode every independent public-API, partial-JSON and shape check used here. Adding such tests later would strengthen repeatability; this revalidation adds no permanent tests.
- _json_dumps_iterative is an internal encoder for the dict/list/scalar structures produced by run_record_to_dict, not a promised replacement for every json.dumps input/extension option. Cyclic arbitrary Python containers are not canonical finite observations.
- Returned JSON is compact and deterministic; consumers must use its schema, not depend on old pretty-print whitespace. Downstream decoders can have their own depth limits; no import/deserialization API is promised by B07.
- Inherited generic dataclass repr/hash/equality and the B05/B06 fingerprint limitations remain outside these fixed public traversal paths. No global recursion-limit change was made.
- The original audit's scope and experimental cautions remain: logical counters/abstract slots are not native instructions/bytes; declared factors do not establish causation; benchmark validity, STG/CBN, GC/lifetime and persisted replay remain future work.

The checkouts, tests and finite probes supply evidence for the supported implementation, not a mathematical proof of every runtime path or scientific experimental validity. No design/specification/ADR decision was changed.

## 8. Final B07 Merge Readiness Recommendation

**Recommend integrating B07 into main, with the explicit nonblocking F03 limitation.** The required production closure conditions for F01/F02 are satisfied: corrected code is present and inspected, original failures no longer reproduce, deep functional/structural cases pass, and the full suite remains green.

The current revision receives **ACCEPTED WITH LIMITATIONS**, rather than an unconditional acceptance, because the requested complete-branch whitespace check still fails. All that remains for F03 closure is the precisely identified EOF-only cleanup and a successful repeat of the whitespace checks. No further production fix is required by this revalidation.

Only `docs/audits/b07-revalidation.md` was created. The original audit hash and HEAD were preserved; no production/test/contract/specification/ADR/planning file was edited, and no commit, merge, branch change or pull request was performed. Temporary coverage files were kept outside the repository and removed after extracting their totals; the repository's pre-existing .coverage was preserved.
