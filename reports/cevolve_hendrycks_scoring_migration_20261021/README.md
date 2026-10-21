# C-EVOLVE / Hendrycks MATH scoring migration

This is an explicit scientific metric replacement. Historical reported scores,
raw responses, sealed memberships and frozen manifests have not been rewritten.
The evidence below is offline; no model API, formal search or A2 Test was run.

## Release status

```json
{
  "IMPLEMENTATION": "COMPLETE",
  "HENDRYCKS_PARITY": "PASS",
  "TWO_REPO_PARITY": "PASS",
  "ONLINE_SCORER_REPLACEMENT": "COMPLETE",
  "HISTORICAL_ARTIFACT_INTEGRITY": "PASS",
  "OFFLINE_REGRESSION": "PASS",
  "REAL_API_CALLS": 0,
  "A2_TEST_RESUMED": "NO",
  "READY_FOR_NEW_EXPERIMENT": "NO"
}
```

## Source and actual rules

The [C-EVOLVE paper](https://arxiv.org/abs/2509.23331), Section 3, Appendix B.2
and Appendix J distinguish consensus aggregation from per-item accuracy and
identify Hendrycks final-answer extraction. The concrete implementation is
pinned to [hendrycks/math commit 985bdc1696e88e8643f081a0ff4719da39f2ae2a](https://github.com/hendrycks/math/tree/985bdc1696e88e8643f081a0ff4719da39f2ae2a):
`modeling/dataset/util.py`, `modeling/math_equivalence.py`, and the `remove_boxed`
helper actually used by `modeling/eval_math_gpt.py`. The upstream MIT license,
URLs, source hashes and helper provenance are included in each scorer package.
This is not a claim of source-level parity with unpublished complete C-EVOLVE code.

The sole current contract is `cevolve_hendrycks_math_v1`. Raw output passes through
original last-box discovery and boxed removal, then original finite normalization
and string comparison. No unboxed Final Answer, last-number, symbolic or LLM
fallback runs. The original fbox-discovery/boxed-only-removal quirk is preserved.
Fraction formatting, integer slash fractions, square-root braces, the special 0.5
case and short variable assignments follow upstream exactly; arbitrary algebra,
rational reduction and numeric tolerance are not added. The upstream exception
branch does literal string comparison, never a different scorer.

Engineering deviations are explicit: missing/empty/non-text/normalization-invalid
gold raises an evaluation-input error, blocking upstream None/None equality;
serialized resource excess raises an input error. Valid gold plus extraction
failure is binary zero. Finish reason is retained metadata and is not an extra
correctness gate. Normal scoring always returns a Boolean correctness result.

## Entry points and retirement

Both repositories have byte-identical `math_scoring` core modules and source
identity. GEPA single-Prompt feedback, optimization/Validation/Test, Optimize60
benchmark correctness and selected team-winner correctness delegate to it. GP
benchmark adapters, current structured team member/final scoring and independent
study brokers use the same core. Parsed-output adapters call the raw scorer.

V7/V5 continuation judges, Unified V1's three policies, MASPO compatibility,
semantic workers and historical certificate-based Test overrides are retired.
Old audit/continuation CLIs cannot select a policy or create providers. Historical
multi-policy calibration scoring/paid execution is disabled. Retained historical
module names are thin current adapters or fail-closed retirement sentinels, not
compatibility execution modes. Recovery inventories, plans, per-file hashes,
archives and tombstones are under `docs/archive/scoring/pre_hendrycks_20261021/`.
Its provenance addendum distinguishes two provisional new helper files from
actual predecessor source; originals remain recoverable without importing archives.

Current cache request identities, durable-cache scope, persisted prediction
records and current MATH bindings include the new contract and source digest.
Old records, source-bound scopes and authorizations are rejected rather than
upgraded. New GEPA config and GP scoring-amendment draft configs retain all
non-scoring search parameters. Historical manifests remain readable, pinned
metadata; that does not grant runtime eligibility.

## Regrading 3,492 saved responses

| Prior contract | Prior correct | New correct | Old true to false | Old false to true | Old unresolved to false |
|---|---:|---:|---:|---:|---:|
| Historical V7 | 2,243 | 355 | 2,101 | 213 | 1 |
| Unified V1 paper extracted exact | 2,331 | 355 | 1,983 | 7 | 0 |
| Unified V1 MASPO compatibility | 344 | 355 | 2 | 13 | 0 |
| Unified V1 bounded semantics | 2,619 | 355 | 2,269 | 5 | 44 |

New outcomes: 355 normalized matches, 152 normalized mismatches, 2,985 extraction
failures, zero unresolved outcomes and zero invalid-gold errors in this corpus.
Every extraction failure lacks either boxed/fbox marker. Of V7's 2,101 newly
incorrect responses, 2,098 fail extraction and 3 differ under normalization.
This large change is predominantly an output-format contract change, not evidence
of a model capability decline. Prompts were not changed to compensate for it.

All 44 formerly unresolved semantic samples now score zero for extraction failure.
That means their saved unboxed outputs fail this contract, not that semantic
mathematical incorrectness has been independently established.

The matched 2,700 terminal subset changes from 2,028 old correct to 148 new correct:
123 retained correct, 1,905 old correct lost, 25 newly correct and 647 unchanged
incorrect. These are explicitly new offline regrades; original grades remain intact.

Each repository independently wrote all 3,492 private rows with sample identity,
response/gold hashes, extraction, normalization, old verdicts, new verdict and
change reasons. Full rows contain saved-answer content and remain private.
Sanitized counters, input/output digests and transitions are in `summary.json`.
Both private result streams have exactly the same SHA-256:

`5b5adffedce8fc33ff792a307069e3b24a9d70f2d7cc1c095a098b52df634acc`.

## Aggregation compatibility

Existing equal-weight plurality and tie-abstention are unchanged. MathVerify is
retained only for gold-blind vote equivalence. For example, x+x and 2x can share
a vote class while only 2x receives correctness against gold 2x under finite
normalization. Reordering the first representative of this class can change the
selected answer's correctness; dedicated tests cover this effect in both repos.
C-EVOLVE strict-majority/random-fallback consensus is a different policy and was
not installed. This migration does not claim complete C-EVOLVE team aggregation.

## Verification and scientific limits

The independent oracle executes pure helpers extracted from pinned upstream
source, with boundary fixtures and AST parity in both Python environments.
Current integration checks cover each scoring lane, cache isolation, historical
record/scope rejection, new-draft preflight and refusal of old Test execution.
Full regression evidence and the final conformance record accompany this report.
Retired-score-specific and historical/private suites are explicitly inventoried;
they are not reported as current passing tests or as full historical replay.

Integrity verification covers 3,520 original input-evidence files, 73 prior audit
artifacts and 15 critical original result files with zero changes. Historical
manifests, initial teams and prior Unified V1 report artifacts match their initial
hashes. The original staged-index diffs were unchanged at the pre-publication integrity check; the later user request explicitly authorizes a task-only publication.

Initial preflight found stale generated LINEAGE and KNOWN_FAILURES views. Only
derived views were regenerated from existing authoritative registries; no failure
record or historical manifest was relaxed. The final governance result is recorded
separately. The preparation is a draft without execution binding, source freeze or API authorization. A later publication commit does not grant execution readiness.

Historical accuracy numbers are not directly comparable across these contracts.
For method comparisons, regrade all saved responses under one declared contract
and distinguish regrading from fresh generation. Existing prompts/memberships
remain unchanged; strict boxed extraction may conflict with old output instructions.
Any new formal experiment needs a fresh protocol/source freeze and exact API
authorization; old A2 Test authorization and checkpoints cannot be resumed here.

No change to non-MATH benchmark scoring, GEPA selection/Pareto logic, candidate
acceptance, team admission, seed, split membership or experiment budgets was made.
This verification snapshot precedes publication. The user subsequently authorized completion and task-only commit/push in both repositories; publication does not authorize model APIs or experiments.

## Completion verification and remaining boundaries

The final GEPA current run passed 355 cases; 18 retired-scoring cases and 4 whole
historical modules were explicitly excluded. The multi-agent complete current
worktree run was 1166 passed, 12 failed, 2 skipped. Eleven failures identified a
fresh-preparation registry/frontier mismatch; this was corrected without altering
historical manifests and all 11 affected governance assertions were rerun.
One remaining failure belongs to the separate, unpublished SiliconFlow work and
is preserved rather than silently fixed. Removing that unrelated 45-case module
and replacing the governance results with the focused post-fix evidence yields
1133 passing and 2 skipped current cases in the publication's reconciled coverage.
This is not claimed as a newly rerun green complete-worktree suite.

Production compileall, isolated package scoring, both upstream oracle suites,
all 10 entry-point replays, deterministic governance/manifest preflight and
sanitization passed. The additional 207-case affected-module run also passed.
The corrected source metadata was checked separately; unchanged scoring/runtime
regression evidence was reused. Full historical/private replay was not run.

The previous KNOWN_FAILURES/LINEAGE drift was corrected by regenerating derived
views. The two repositories' scoring cores and all 3,492 row results agree exactly.
There are no unresolved scoring-migration blockers. Readiness remains NO because
no new exact experiment source/phase freeze, binding, handoff or API authorization
exists. Publication alone does not open Validation/Test or resume A2.

- [Verification counts, omissions and evidence hashes](verification.json)
- [Entry-point/core and integrity conformance](conformance.json)
- [Aggregation versus correctness compatibility](aggregation_scoring_compatibility.md)
- [Published task file inventory](changed_files.json)

The contract source digest is
`c4a1166c3ab181bd7b4c92302584f20a40ba92e6bf7db2061d1f9c2fa6ac1b34`.

Publication addendum: the immutable predecessor audit is now registered as inactive evidence; its old config path is an execution-disabled archive tombstone. Task-index scoring core probes reproduce the verified digest in both Python environments. See [publication metadata checks](publication_metadata.json).
