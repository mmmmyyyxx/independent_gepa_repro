# Implementation status

Updated: 2026-08-24

## Current milestone

The V17-matched Independent-GEPA implementation and formal three-seed run are
complete. All 15 official GEPA member searches, three post-freeze development
evaluations, and three frozen-test evaluations finished under the frozen
protocol. The sanitized report decision is
`CONTINUE_NO_STRONG_BASELINE_PRESSURE`.

## Frozen protocol

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
- `python -m pytest -q`: PASS, 56 tests.
- `python -m compileall -q src scripts tests`: PASS.
- Deterministic report replay and public leakage audit: PASS.
- `git diff --check`: PASS.

## Decision

**CONTINUE / no strong baseline pressure.** Independent-GEPA did not beat S4
on any seed and also trailed Generic S1 on mean frozen-test VoteAcc. This is an
internal research decision under the frozen comparison, not a statistical
significance claim and not an instruction to modify the sibling repository.
