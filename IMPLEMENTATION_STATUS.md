# Implementation status

Updated: 2026-08-06

## Current milestone

Stage-two bundle-protocol compatibility preparation is complete. The real
Seed46 bundle is exported and passes Pilot/Canary offline preflight under
Python 3.11. Formal three-seed readiness remains HOLD because its logical
budget is intentionally not frozen.

## Verified facts

- Real API calls authorized for this task: **no**.
- Real API calls made: **0**.
- `vendor/gepa` HEAD:
  `b4dbb55b7601dac448cdb836d5a401ca7d9eb920`.
- The fixed source exposes `gepa.optimize`, `GEPAAdapter`,
  `EvaluationBatch`, and `GEPAResult`.
- `gepa.optimize` supports Pareto candidate selection, instance frontier,
  reflection minibatches, merge controls, `run_dir`, automatic
  `gepa_state.bin` resume, `max_metric_calls`, deterministic seed, and full
  validation evaluation.
- The real Seed46 bundle exists at
  `D:\myx\grade_one\experiments\comparison_bundles\disambiguation_qa_seed46_v1`
  with overall hash
  `eddbdb90cb964b528c8c289d8fb720f21ff2b1c26cd80f5ba884a7a9eafff836`.
- The `independent_gepa` Conda environment uses Python 3.11.15.
- Bundle schema v2 preserves raw CSV hashes while normalizing LF/CRLF/CR
  field newlines into deterministic canonical JSONL.
- Parser contract v2 reproduces `task_parser_v1`, including per-example
  option domains, duplicate-final-answer rejection, and source failure types.
- Initial optimization metrics are frozen at five times 60/75 and team 60/75;
  development and test are explicitly `not_evaluated`.
- Shared task-model transport, reference optimizer role metadata, and native
  GEPA reflection configuration are separate frozen contract sections.
- The audited Seed46 Pilot logical budget is 1611, allocated as 322 per member
  with one unused evaluation. Formal budget status is `not_frozen`.
- The fixed GEPA internal metric counter excludes old/new reflection-minibatch
  task calls. Fair accounting is therefore enforced by the independent
  per-member `BudgetLedger`, atomic batch admission, and a ledger-aware GEPA
  stop callback. The public logical count comes from that ledger.
- Logical ledgers are atomically persisted per member. Completed members resume
  from identity-checked private results with zero new requests; interrupted
  fixed-GEPA resumes count its mandatory seed re-evaluation.
- The runner supports a member-0-only canary without freezing a partial team,
  and five-member Pilot/Formal runs with direct best-candidate composition.

## Offline gate results

- `python -m compileall -q src scripts tests`: PASS.
- `python -m pytest -q`: PASS, 48 tests.
- `python scripts/verify_environment.py`: PASS.
- Real bundle validation (75/50/125): PASS.
- Real bundle Pilot and Canary offline preflight: PASS.
- Formal preflight: expected rejection, `formal logical budget is not frozen`.
- True source export determinism: PASS.
- Source parser parity: PASS, 12 frozen fixtures.
- All seven CLI `--help` paths: PASS.
- `git diff --check`: PASS.
- Real task-model requests: 0.
- Real reflection-model requests: 0.
- Logical experiment budget consumed: 0. Fake-test accounting is test-only.

## Remaining before an online canary

- Obtain explicit authorization for real API calls.
- Use an external run config with config-level API opt-in plus the CLI
  `--allow-real-api` opt-in; committed configs remain API-disabled.

Decision for Seed46 Canary/Pilot preparation: **GO** after explicit API
authorization. Decision for Formal three-seed work: **HOLD** until a formal
logical budget is frozen. No online stage or accuracy evaluation has run.
