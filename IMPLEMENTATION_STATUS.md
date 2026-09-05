# Implementation status

Updated: 2026-09-05

## Capacity-probe milestone

The standalone official-GEPA single-prompt capacity probe is complete for
seeds 75/76/77. It is intentionally outside the historical matched five-member
baseline and does not alter its budget, data, prompt-team evaluation, or
results. The new stage uses train/optimizer-validation folds of 100/50,
ExternalValidation50 only after candidate freeze, and an identity-only
inaccessible Test50.

- All folds terminated `no_improvement_patience_10` and are `SATURATED`.
- Seed 75: OptimizerVal 0.40 -> 0.70; ExternalValidation 0.62 -> 0.66;
  frontier oracle 0.76 (complementarity gap +0.10).
- Seed 76: OptimizerVal 0.58 -> 0.72; ExternalValidation 0.62 -> 0.74;
  selected candidate equals frontier oracle.
- Seed 77: OptimizerVal 0.60 -> 0.80; ExternalValidation 0.60 -> 0.72;
  selected candidate equals frontier oracle.
- Aggregate accounting: 3,596 task-example evaluations, 66 reflection calls,
  3,662 real requests, 6,411,791 tokens, estimated CNY 4.8786658.
- Public sanitized evidence: `experiments/gepa_single_prompt_capacity_20260905`.
  Private bundle, prompts, raw outputs, GEPA checkpoints, and caches remain
  ignored. Test50 was never loaded.

## Current milestone

The subsequent-experiment model profile is implemented and its minimal real
provider smoke is complete. Solver rollouts now use `qwen3-8b` with thinking
disabled. Evaluator, prompt optimizer, and reflection identities are all
`qwen3.7-flash`. No GEPA search, frontier, candidate-generation, stopper,
budget, split, prompt, seed, parser, or scoring setting changed.

The completed August 24 V17 run and its sanitized report remain immutable
historical qwen3-14b results with decision
`CONTINUE_NO_STRONG_BASELINE_PRESSURE`.

## Model-routing smoke

- Seed 56, member 0, five optimization examples; development and test disabled.
- Solver: `qwen3-8b`, thinking false, 9 real requests, 6,019 tokens.
- Optimizer/reflection: `qwen3.7-flash`, 2 real requests, 2,701 tokens.
- Correctness evaluator: strict parser plus gold comparison; 0 LLM judge calls.
- Total: 13 logical task-example evaluations, 11 real requests, 8,720 tokens,
  30.44 seconds, estimated CNY 0.0066682.
- Three seed-specific derived bundles passed formal validation and retained
  byte-identical prompt, split, parser, budget, and reference-result files.
- Sanitized evidence: `reports/model_routing_smoke_20260903.json`.
- The 2026-09-04 qwen3-14b smoke remains historical only and is superseded by
  this corrected model profile.

## Historical frozen protocol

- Model: `qwen3-14b`; thinking false; temperature 0; max tokens 1800.
- Seeds 56/57/58; frozen splits 75 optimization / 50 development / 125 test.
- Five shared-identical initial prompts per seed and five isolated official
  GEPA v0.1.1 runs using seeds `experiment_seed * 1000 + member_id`.
- Search feedback is current-member strict correctness only. Development and
  test are inaccessible until the five prompts are frozen.
- Primary cap is the corresponding V17 S4 realized task-plus-reflection token
  count, divided equally across members, with a 5% hard ceiling.
- Initial parity policy `identity_and_same_run_member_vector_v2` freezes all
  request identities and requires five identical members to agree in the
  current canonical evaluation. Historical output differences are diagnostic;
  no replay result was cherry-picked.

## Formal results

- Independent-GEPA validation VoteAcc: 0.660 / 0.660 / 0.680; mean 0.6667.
- Independent-GEPA frozen-test VoteAcc: 0.680 / 0.672 / 0.680; mean 0.6773.
- S0/S1/S4 frozen-test means: 0.6827 / 0.7120 / 0.7067.
- Independent-GEPA minus S1: -0.0347 mean, 0/1/2 W/T/L.
- Independent-GEPA minus S4: -0.0293 mean, 0/0/3 W/T/L.
- Search tokens: 453,789 / 428,577 / 428,260; aggregate GEPA/S4 compute
  ratio 0.7986. Every seed stayed below its target and hard limit.
- Search accounting: 2,673 logical task evaluations, 2,445 provider calls,
  60 reflection calls, and 1,310,626 total model tokens.
- Entire authorized online workflow, including parity, smoke, development and
  frozen test: 4,081 successful requests and 2,163,638 tokens; estimated cost
  CNY 3.149951 under the frozen CNY 1/M input and CNY 4/M output prices.

## Verification

- GEPA tag/commit/import path and clean vendor checkout: PASS.
- Three bundle schema/hash/disjointness/formal-budget validations: PASS.
- Parser, feedback isolation, member state isolation, split access, budget,
  cache, operational failure, resume, final composition, reporting and
  sanitization tests: PASS.
- Split-role bundle/formal model routing validation: PASS.
- Minimal real model-routing smoke: PASS.
- `python -m pytest -q`: PASS, 58 tests.
- `python -m compileall -q src scripts tests`: PASS.
- Deterministic report replay and public leakage audit: PASS.
- `git diff --check`: PASS.

## Decision

**CONTINUE / no strong baseline pressure.** Independent-GEPA did not beat S4
on any seed and also trailed Generic S1 on mean frozen-test VoteAcc. This is an
internal research decision under the frozen comparison, not a statistical
significance claim and not an instruction to modify the sibling repository.
