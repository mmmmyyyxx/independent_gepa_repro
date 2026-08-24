# Implementation status

Updated: 2026-08-24

## Current milestone

The V17-matched implementation, offline gates, real transport smoke, and all
five independent Seed56 GEPA searches are complete. The attempted formal run
is **HOLD / incomplete** because Seed57 initial-state parity reproduced 50/75
instead of the frozen V17 value 51/75. No Seed57 GEPA search and no Seed58
evaluation/search were started.

## Frozen protocol

- Model: `qwen3-14b`; thinking false; temperature 0; max tokens 1800.
- Seeds: 56, 57, 58; splits: 75 optimization, 50 development, 125 test.
- Five shared-identical starting prompts per seed; five isolated official GEPA
  v0.1.1 runs with seeds `experiment_seed * 1000 + member_id`.
- Search feedback is current-member strict correctness only. Development and
  test are unavailable during search.
- Primary budget: V17 S4 realized task-plus-reflection tokens, equal fifths,
  with a calibrated 45,000-token per-member stop reserve and 5% hard ceiling.
- Final team: direct five independent best candidates, equal plurality, ties
  abstain/incorrect. Development must be sealed before the one permitted test.

## Execution status

- Phase A/bundle/preflight: PASS.
- Seed56 initial aggregate parity: PASS at 50/75. Historical per-example vector
  differed and is retained as a non-blocking backend-replay diagnostic.
- Phase B smoke: PASS; 13 logical evaluations, 11 real requests, 6,654 tokens.
- Seed56 formal search: PASS; five members frozen, 900 logical evaluations,
  835 real requests, 25 reflection calls, 453,789 tokens, 593.83 seconds.
- Seed56 development: team 0.660. Seed56 test: team 0.680.
- Seed57 initial aggregate parity: HOLD at 50/75 versus frozen 51/75.
- Seed57 search: not started. Seed58: not started.
- Three-seed comparison and research decision: unavailable by protocol.

## Verification

- GEPA tag/commit/import path and clean vendor checkout: PASS.
- Three frozen V17 bundle schema/hash/disjointness checks: PASS.
- Parser, isolation, access, budget, cache, failure, resume, composition,
  sanitization, fake five-member E2E and CLI tests: PASS.
- `python -m pytest -q`: PASS (54 tests after the cache-concurrency regression).
- `python -m compileall -q src scripts tests`: PASS.
- `git diff --check`: PASS.

## Decision

**HOLD.** The available Seed56 result is valid single-seed evidence but must not
be generalized. Resume only under an explicitly approved parity policy or a
new frozen provider-replay contract; do not repeatedly sample until the old
51/75 outcome happens.
