# AGENTS.md — Independent-GEPA Reproduction

## 1. Repository purpose

This repository reproduces **Independent-GEPA under a matched prompt-team evaluation protocol**.

The scientific question is:

> If each of five prompts is optimized independently for its own task accuracy, does the resulting five-member voting team match or outperform the member-aware joint optimization method in `multi_agent_diversity`?

This repository is an **external baseline implementation**, not a branch, setting, or ablation of `multi_agent_diversity`.

Do not copy the joint optimization logic from `multi_agent_diversity` into this repository.

---

## 2. Fixed upstream GEPA identity

Use the official GEPA repository only:

- Repository: `gepa-ai/gepa`
- Tag: `v0.1.1`
- Commit: `b4dbb55b7601dac448cdb836d5a401ca7d9eb920`
- Expected location: `vendor/gepa`

Rules:

1. `vendor/gepa` is read-only.
2. Never edit files inside `vendor/gepa`.
3. Before any implementation or experiment, verify:
   - `vendor/gepa` exists;
   - its HEAD equals the fixed commit;
   - its working tree is clean;
   - the imported `gepa` package resolves to `vendor/gepa`, not PyPI or another checkout.
4. Do not silently upgrade to `main` or another release.
5. If the fixed checkout lacks an assumed API, inspect its source and adapt this repository. Do not modify upstream GEPA.

---

## 3. Relationship to `multi_agent_diversity`

The sibling repository is expected at:

```text
D:\myx\grade_one\experiments\multi_agent_diversity
```

It is read-only from this repository.

`multi_agent_diversity` is the source of truth only for the **comparison contract**:

- task and seed identities;
- optimization/development/test split IDs and hashes;
- five initial prompt identities and member ordering;
- model configuration;
- strict answer parser behavior;
- plurality voting and tie handling;
- reference task-model evaluation budget;
- reference method result metadata;
- final reporting metrics.

It is **not** a runtime Python dependency.

Forbidden:

- importing Python modules from `multi_agent_diversity`;
- adding its path to `PYTHONPATH` during formal runs;
- reading its live run directories during optimization;
- copying its member-aware responsibility, team feedback, RCRU, Pareto-update, or dual-target code;
- treating Independent-GEPA as one of its internal settings.

Alignment is achieved through a frozen, validated **comparison bundle**, not shared optimizer code.

---

## 4. Comparison bundle contract

Formal runs may read only a frozen bundle, expected under a path such as:

```text
D:\myx\grade_one\experiments\comparison_bundles\<bundle_id>
```

A valid bundle must contain enough information to reproduce the comparison without importing the sibling repository.

Minimum bundle content:

```text
manifest.json
model_contract.json
parser_contract.json
budget_reference.json
initialization/
  agent_0.txt
  agent_1.txt
  agent_2.txt
  agent_3.txt
  agent_4.txt
splits/
  optimization.jsonl
  development.jsonl
  test.jsonl
hashes.json
```

The validator must check:

- canonical schema version;
- task identity;
- experiment seed;
- exactly five members;
- expected split sizes;
- split disjointness;
- stable member-to-prompt mapping;
- prompt hashes;
- example IDs and file hashes;
- model contract;
- parser contract;
- voting contract;
- budget contract;
- overall bundle hash.

Formal target configuration:

```text
Task: disambiguation_qa
Members: 5
Optimization: 75 examples
Development: 50 examples
Test: 125 examples
Formal seeds: 44, 45, 46
Canary/Pilot seed: 46
Task model: qwen3.7-flash-2026-07-15
Reflection model: qwen3.7-flash-2026-07-15
enable_thinking: false
Voting: plurality
Tie rule: abstain / incorrect, exactly as defined by the bundle
```

Do not hard-code source-project commit IDs or method-version names into optimizer logic. Treat them as opaque experiment identity fields from the bundle.

---

## 5. Definition of Independent-GEPA

For experiment seed `s`, optimize five members independently:

```text
Member 0: one GEPA run
Member 1: one GEPA run
Member 2: one GEPA run
Member 3: one GEPA run
Member 4: one GEPA run
```

Each run starts from that member's frozen initial prompt.

Each run has its own:

- GEPA seed;
- candidate pool;
- Pareto state;
- reflection history;
- run directory;
- checkpoint;
- artifacts;
- budget ledger.

Recommended deterministic GEPA seed:

```text
gepa_seed = experiment_seed * 1000 + member_id
```

The optimized candidate has exactly one mutable component:

```python
{"system_prompt": "..."}
```

The optimization metric is only the current member's strict per-example correctness:

```text
valid and correct -> 1.0
wrong or terminal invalid -> 0.0
operational/provider failure -> exception, not score 0
```

The final team is formed directly from the five independent best candidates:

```text
final_team[i] = best_candidate_from_member_i_run
```

Forbidden:

- team-vote feedback during GEPA search;
- peer answers or peer prompts in feedback;
- `G`, `H`, `M`, responsibility, active-lane, coalition, same-wrong, member-gain, or pivotality signals;
- sharing candidates or reflections across members;
- searching combinations of member candidates;
- replacing a member's independent best candidate because another candidate gives better team vote;
- jointly optimizing the final five prompts;
- giving additional budget to weak or unsuccessful members.

These constraints define the baseline. Violating them changes the method into a team-level GEPA variant.

---

## 6. Data-access policy

### During GEPA optimization

Allowed:

- optimization split only;
- gold labels from the optimization split;
- the current member's prompt, response, parser result, and correctness feedback.

Forbidden:

- development split;
- test split;
- peer outputs;
- final team metrics;
- source-project run artifacts.

Protocol-matched GEPA configuration:

- `trainset` uses the 75 optimization examples;
- if the fixed GEPA API requires a validation set, use the same 75 optimization examples;
- do not use the separate 50-example development split for candidate selection.

### After all five member searches finish

- freeze the five best prompts;
- development may be evaluated once for a Pilot report;
- development results must not modify prompts, budget, configuration, or candidate selection.

### Formal test

- test is evaluated only after all five prompts for that seed are frozen;
- test is evaluated once per formal seed;
- test results must never flow back into optimization.

Any access violation invalidates the run.

---

## 7. Parser and evaluation alignment

Do not invent a new answer parser.

The evaluator must implement the exact behavior described by `parser_contract.json`, including:

- legal option range;
- accepted final-answer formats;
- conflict handling;
- empty output handling;
- truncation handling;
- terminal-invalid classification;
- case and whitespace normalization.

Maintain golden parser fixtures exported from the comparison contract.

Parser parity is a hard requirement:

```text
parsed option
valid / invalid
correct / incorrect
failure type
```

must match the frozen reference fixtures exactly.

The final evaluator must use the bundle-defined:

- member ordering;
- plurality aggregation;
- tie-as-abstain behavior;
- invalid-answer behavior.

Do not use a GEPA sample metric or an ad hoc substring matcher for final reporting.

---

## 8. Model-provider contract

Use an OpenAI-compatible provider for Alibaba Cloud Model Studio / DashScope.

Configuration comes from environment variables and bundle/config files. Never hard-code credentials.

Required behavior:

- fixed task and reflection model snapshots;
- `enable_thinking = false`;
- explicit temperature, max tokens, timeout, and retry settings;
- exact-request cache;
- separate accounting for logical evaluations and real API requests;
- prompt/completion/total-token accounting by role;
- response truncation and finish-reason logging;
- no credential, private endpoint, or full request-body leakage in public artifacts.

Operational failures must remain distinct from model errors:

- provider/network/schema failure: retry or fail the run according to policy;
- valid but wrong answer: score 0;
- terminal invalid answer: score 0.

Allowed automatic retry is limited to transient failures such as timeouts, 408, 429, 500, 502, 503, or 504.

Do not automatically retry credential, model-not-found, or request-contract errors.

---

## 9. Fair-budget contract

The primary comparison budget is:

```text
logical task-example evaluations
```

Do not compare methods by number of outer iterations.

The bundle provides the reference budget from `multi_agent_diversity`.

For a total budget `B`:

```text
member_budget = floor(B / 5)
```

Use the same member budget for all five members.

Count all task-example evaluations performed by GEPA, including:

- seed candidate evaluation;
- minibatch evaluation;
- full-set evaluation;
- merge candidate evaluation;
- re-evaluation after resume when logically performed.

A cache hit still counts as a logical task-example evaluation, although it does not count as a real API request.

Always report:

- logical task-example evaluations;
- real task-model requests;
- reflection-model calls;
- task-model prompt/completion tokens;
- reflection-model prompt/completion tokens;
- total tokens;
- estimated or actual cost;
- wall-clock time.

Do not increase budget after seeing results.

---

## 10. Required result metrics

Optimization uses only individual correctness, but final reporting must align with the prompt-team evaluation in `multi_agent_diversity`.

Report for each seed:

- team vote accuracy;
- five individual accuracies;
- mean member accuracy;
- minimum member accuracy;
- oracle coverage;
- oracle-covered but vote-wrong count/rate;
- number of members improved over initialization (`N+`);
- per-member gain over initialization;
- invalid rate;
- logical evaluations;
- real requests;
- tokens, cost, and wall-clock time.

Where supported by the frozen evaluator, also report diagnostic—not optimization—metrics:

- mean `G`, `H`, and vote margin;
- pairwise correctness correlation;
- same-wrong agreement or excess;
- high-order team-wrong rate.

Do not expose team diagnostics to GEPA reflection or candidate selection.

The source project distinguishes individual prompt strength from joint team behavior; this baseline must preserve that distinction by optimizing independently and evaluating jointly only after search.

---

## 11. Private and public artifacts

Private run artifacts may contain full prompts, examples, gold labels, and raw model outputs only under ignored local directories.

Public/sanitized artifacts must not contain:

- full initial or optimized prompts;
- question text;
- choices or gold answers;
- raw model responses;
- API keys;
- private endpoints;
- exact cache content;
- machine-specific absolute paths.

Public artifacts may contain:

- hashes;
- IDs;
- aggregate metrics;
- token and cost statistics;
- candidate counts;
- completion and audit status;
- protocol/version identities.

Before any commit, run a leakage audit.

---

## 12. Repository boundaries and preferred structure

Keep the implementation self-contained and small.

Preferred modules:

```text
src/independent_gepa/
  versions.py
  protocol.py
  bundle.py
  parser.py
  provider.py
  evaluator.py
  adapter.py
  feedback.py
  budget.py
  runner.py
  final_evaluator.py
  artifacts.py
  audit.py
```

Preferred scripts:

```text
scripts/verify_environment.py
scripts/export_comparison_bundle.py
scripts/validate_comparison_bundle.py
scripts/preflight.py
scripts/run_independent_gepa.py
scripts/evaluate_final_team.py
scripts/audit_run.py
```

Do not create a general multi-method framework. This repository implements Independent-GEPA only.

Avoid large files with method-name conditionals. Prefer small typed components with explicit contracts.

---

## 13. Coding rules

- Python target: 3.11.
- Use type hints for public functions and dataclasses for stable records.
- Prefer deterministic, canonical JSON serialization.
- Use stable ordering for examples, members, candidates, and artifacts.
- Treat identities and hashes as first-class fields.
- Validate configuration before API calls.
- Raise explicit exceptions for protocol violations.
- Do not silently recover from identity, data-leakage, or budget errors.
- Do not weaken tests to make implementation pass.
- Do not invent missing bundle fields; report the gap.
- Do not change experiment semantics without explicit user approval.

When the fixed GEPA API differs from expectations, inspect its source/tests and document the actual adapter contract used.

---

## 14. Default work procedure for Codex

At the start of every task:

1. Read this file.
2. Read `README.md`, `IMPLEMENTATION_STATUS.md`, and the relevant config.
3. Run `git status --short`.
4. Verify the pinned GEPA checkout and import path.
5. Inspect existing implementation and tests before editing.
6. State whether real API calls are allowed for the current task.

During work:

- proceed autonomously through ordinary implementation decisions;
- avoid asking for confirmation on low-risk details already fixed here;
- stop and ask only when a missing decision would change scientific comparability, data access, budget, or test usage;
- update `IMPLEMENTATION_STATUS.md` after major milestones;
- keep changes within this repository;
- never commit or push unless explicitly requested.

At the end of every task, report:

- files changed;
- implemented behavior;
- tests and commands run;
- test results;
- API calls made;
- budget consumed, if any;
- remaining risks;
- `git status --short`;
- GO/HOLD decision for the next stage.

---

## 15. Required offline gates

Before any real API call, all of the following must pass:

```text
GEPA commit and import-path verification
bundle schema/hash/disjointness validation
parser parity tests
individual-feedback isolation tests
member state and run-directory isolation tests
optimization/development/test access tests
logical-budget accounting tests
cache accounting tests
operational-failure semantics tests
checkpoint/resume identity tests
final-team composition tests
artifact sanitization tests
fake five-member end-to-end optimization
CLI --help tests
compileall
pytest
git diff --check
```

Recommended commands:

```powershell
python -m compileall -q src scripts tests
python -m pytest -q
python scripts/verify_environment.py
python scripts/preflight.py --offline ...
git diff --check
git status --short
```

Real API calls before these gates pass are prohibited.

---

## 16. Online-stage gates

### Canary

- seed 46;
- member 0 only;
- five fixed optimization examples;
- development disabled;
- test disabled;
- very small fixed logical-evaluation budget;
- verify task-model and reflection-model transport, parser, tokens, artifacts, and resume.

### Pilot

- seed 46;
- all five members;
- 75 optimization examples;
- one development evaluation only after all prompts are frozen;
- test disabled;
- fixed fraction of the formal matched budget.

After Pilot, stop and report. Do not start formal three-seed runs without explicit user approval.

### Formal

- seeds 44, 45, and 46;
- all five members;
- full frozen matched budget;
- no development-based selection;
- one test evaluation after each seed's five prompts are frozen;
- no cross-seed or cross-member sharing.

---

## 17. Hard stop conditions

Immediately stop the current stage and report HOLD if any of the following occurs:

- GEPA identity mismatch or dirty upstream checkout;
- comparison-bundle hash or schema mismatch;
- split overlap or unexpected example count;
- parser parity failure;
- development or test access during optimization;
- team/peer information entering GEPA feedback;
- candidate or reflection state shared across members;
- cross-member candidate combination search;
- logical budget overrun;
- checkpoint identity mismatch;
- test evaluated before final prompt freeze;
- source/config changes after experiment identity freeze;
- artifact leakage;
- repeated non-transient provider or schema failure;
- result cannot be reconciled with the frozen final evaluator.

Poor accuracy alone is not a protocol failure. Complete the permitted stage and report it honestly.

---

## 18. Scientific interpretation boundary

Independent-GEPA is a pressure test of the premise that independent prompt optimization is insufficient for prompt-team optimization.

A result may support one of several conclusions:

- higher individual accuracy and higher team vote: independent optimization is a strong competitor;
- higher individual accuracy but weaker team vote: joint answer structure remains important;
- similar vote but lower cost: GEPA is more budget-efficient;
- similar vote but worse minimum-member gain or `N+`: methods optimize different team objectives;
- worse results: do not assume the joint method is superior until budget, protocol, and implementation parity are audited.

Do not claim that Independent-GEPA reproduces the original GEPA paper's benchmark results. The correct name is:

> **Independent-GEPA under a matched prompt-team evaluation protocol**
