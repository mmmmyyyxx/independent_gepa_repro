# Implementation status

Updated: 2026-08-06

## Current milestone

Stage-one offline implementation is complete. All required implementation
paths, fake-model gates, and repository-level offline checks pass.

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
- The shared `D:\myx\grade_one\experiments\comparison_bundles` directory did
  not exist at task start. Offline tests will use generated synthetic bundles;
  formal experiment readiness still requires a separately exported and
  validated frozen bundle.
- Host Python is 3.13.5; project target remains Python 3.11. Compatibility is
  tested here, but a Python 3.11 gate remains required before online work.
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
- `python -m pytest -q`: PASS, 40 tests.
- `python scripts/verify_environment.py`: PASS.
- Synthetic formal bundle validation (75/50/125): PASS.
- `python scripts/preflight.py --offline ...`: PASS on the ignored synthetic
  formal fixture.
- All seven CLI `--help` paths: PASS.
- `git diff --check`: PASS.
- Real task-model requests: 0.
- Real reflection-model requests: 0.
- Logical experiment budget consumed: 0. Fake-test accounting is test-only.

## Remaining before an online canary

- Export the actual seed-46 comparison bundle from a source-approved data-only
  specification. The required shared bundle directory was absent at task start,
  and missing fields are not invented.
- Validate the actual source parser golden fixtures, prompt identities,
  reference budget, and initial development/test accuracy metadata.
- Re-run all gates under Python 3.11.
- Obtain explicit authorization for real API calls and use an external config
  with both config-level and CLI-level opt-in.

Decision for stage two: **HOLD** until the actual frozen comparison bundle is
provided/exported and passes validation. No accuracy result or online stage has
been attempted.
