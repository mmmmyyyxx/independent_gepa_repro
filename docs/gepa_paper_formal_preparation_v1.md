# Five-task GEPA formal launch preparation

This completes the offline handoff for the [Qwen optimizer V2 protocol](gepa_paper_five_task_reproduction_qwen37_v2.md).
The experiment still uses the pinned author engine, native Pareto without Merge,
OpenLux GPT-4.1 Mini Solver, Qwen3.7-Flash reflection, author seed0 and one run per
task. Data, prompts, scoring, selection and native search thresholds are unchanged.
The optimizer substitution and existing data/Windows limitations remain disclosed.

## Runtime repair and verification

The author DSPy `Evaluate` returns `(overall_score, result_triples, individual_scores)`
when both output flags are enabled. Each result triple contains
`(example, prediction, score)`. The runner now extracts the prediction before
serializing the private Test profile. The previous adapter attempted to convert
the entire triple to a dictionary, which could fail after paid evaluation.
Scoring and candidate selection are unchanged by this persistence repair.

The new socket-blocked `--lifecycle-only` verification executes the actual runner
for Canary, native search, baseline and selected Test, using original AIME program
and scoring code with synthetic data and fake provider replies. It checks saved
predictions, final program loading, role separation, split access and eight
before/after validation calls. Its synthetic-only authorization validator is a
test fixture; it does not establish a real clean-source freeze or API permission.

## Read-only preflight and proposed phases

The preparation CLI adds `run-pack`. It reads the pinned source/config/manifest
bindings, all15 data files and2,852 rows,159 local NLP resource hashes,146 Python
environment versions, Wikipedia corpus hash and any completed BM25 index receipt.
It imports no model client. Deployment evidence contains four presence booleans;
key and endpoint values are rejected. No positive API grant is generated.

See the [main worktree preflight](../experiments/preparations/gepa_paper_formal_preparation_20261031/preflight.json)
and [proposed phase plan](../experiments/preparations/gepa_paper_formal_preparation_20261031/phase_plan.proposed.json).
There are16 proposed cells: one two-role canary, five searches, five initial-program
Test baselines and five selected-program Test evaluations. Complete all searches
and freeze selections before evaluating Test. Test observations cannot modify
search, model selection or budget decisions. Cache identity remains task/source/
data/model/deployment-bound and permits original identical-request reuse.

The five native search thresholds sum to21,193. Baseline plus selected Test use
2,340 logical rows. Native skip/overshoot semantics are preserved. Additional
operational ceilings below are proposals for explicit review, not active changes:

- Canary:1 logical safety allowance,18 physical attempts,3,000 seconds.
- Search per task:logical safety limit `2 * (native_threshold + Validation_rows + 6)`;
  physical safety limit `9 * (2 * predictors + 1) * logical_limit`;72 hours.
- Each baseline/selected Test:logical limit equal to Test rows;physical limit
  `9 * 2 * predictors * Test_rows`;24 hours.

The factor9 allows the initial call and eight transient retries;the factor2
allows the original adapter's fallback. These bounds are not promised spend,
token ceilings or new native search stopping rules. A safety-cap hit aborts the
attempt and requires review;it never converts an interrupted run to COMPLETE.
No monetary prices are assumed. Record successful usage by role and unknown
failed-attempt usage separately. Future exact grants require user-approved caps.

## Isolated release candidate and Windows paths

A local detached worktree stages the paper-only changes on the committed parent.
It contains no unrelated main-worktree source edits. No commit, push or real API
call is performed. Its source/data/NLP/corpus/environment identities are checked
independently. Private immutable resources are local copies or hardlinks;do not
edit the linked data/corpus/NLP files. The existing isolated Python environment
is reused and its observed versions checked.

A deeply nested initial candidate exposed Windows filename-length failures when
writing authorization/response artifacts. Its failed verification evidence is
retained. The active candidate uses a short sibling worktree and separately passes
the actual four-phase persistence rehearsal. Exact future scopes and complete
artifact paths must match this verified layout, not the abandoned nested layout.
The private handoff records the concrete candidate and interpreter paths.

Before a later authorized local commit, verify the candidate inventory, source
hashes and task-only diff;stage only the declared paper files. Refresh the freeze
and exact source SHA after committing. Do not commit unrelated main-worktree
changes merely to satisfy a clean-tree requirement.

## Remaining launch conditions

`READY_TO_RUN=false`. Local preparation does not resolve these conditions:

1. Supply `OPENLUX_API_KEY` and `OPENLUX_BASE_URL` in the execution environment.
   The audit observed the existing LWJ variables but did not reveal values.
2. Explicitly authorize a local source commit. The repository instruction says
   "never commit or push unless explicitly requested";preparation alone is not
   commit authorization. Source must then be clean and frozen to its real SHA.
3. Authorize the exact dual-role canary after source/deployment/caps are frozen.
   A successful synthetic rehearsal is not a real model-availability check.
4. Build/freeze the full BM25 index for HotpotQA and HoVer when sufficient memory
   is available. Its8GiB free-memory guard and the user's deferral remain in force.
5. Authorize the exact search and final-evaluation scopes after required gates pass.

The three nonretrieval tasks can be released independently once their applicable
conditions pass. No existing historical authorization or checkpoint is reusable.

## Reproduction

```powershell
python scripts/verify_gepa_paper_suite_offline.py cli -- scripts/prepare_gepa_paper_suite.py run-pack --output runs/fresh_launch_pack
python scripts/verify_gepa_paper_suite_offline.py integration --python runs/gepa_paper_suite_20261031/venv/Scripts/python.exe --lifecycle-only --output runs/fresh_lifecycle.json
python scripts/verify_gepa_paper_suite_offline.py pytest -q
python scripts/verify_gepa_paper_suite_offline.py compile
```

Use fresh output paths. For the isolated candidate, use the concrete existing
Python interpreter and resource workspace recorded in the private handoff.
The [completion report](../reports/gepa_paper_formal_preparation_20261031/README.md)
distinguishes main/candidate checks, reused evidence and pending real launch gates.
