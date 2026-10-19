# GEPA V6 offline engineering review

The V6 default entrypoint implements the requested native current-best/Pareto
comparison with a hard3000 native logical-evaluation cap per cell. Seed42,
three repeats per arm, original Optimize150/Validation100, model/decoding and
native search semantics are preserved. No V6 model experiment has started.
No Git commit, push or historical authorization reuse is permitted by this task.

The user's subsequent instruction removes monetary accounting: report input,
output, failed/unknown conservative token bounds, model calls, cache and wall
time; do not estimate currency. Always label the comparison:

**Matched solver-evaluation budget, not exactly matched total compute.**

Final verification: **336 current tests passed**, including33 dedicated V6
cases, production compileall and complete offline preflight. **5346/5346** old
scores replayed unchanged. Real model requests/tokens: **0/0**.

## Deliverables

1. [V6 protocol](../../docs/gepa_single_prompt_math_v6.md) and
   [preparation registration](../../experiments/protocols/gepa_single_prompt_math_v6/proposal.json).
2. [Implementation review and source identities](implementation_review.json).
3. [Complete offline verification](offline_gates.json) and
   [5346-score replay](scoring_parity.json).
4. [Token accounting specification](../../docs/gepa_single_prompt_compute_v6.md).
5. [Readiness decision](readiness.json) and
   [held-out provenance assessment](heldout_assessment.json).
6. [Preregistered analysis template](../../docs/gepa_single_prompt_analysis_v6.md).

## Implemented boundaries

An outcome-blind106-call complete-iteration reserve precedes each native
iteration; every native batch is also atomically admitted before dispatch.
The native optimizer may leave0-105 calls unused, with actual use and stop
reason reported. No partial Full, fabricated score, ordinary rejection on
budget failure, custom selector, archive pruning or20-round cap remains.
Deterministic mock comparisons verify the wrapper preserves native candidate,
lineage, validation and evaluation histories before its budget binds.

The unchanged V5 mathematical algorithm is bound to every search/evaluation/
audit phase. All5346 prior grades were newly replayed through this binding
without a single score change or parent-cache edit. An unresolved computation
is preserved as a failure, never a wrong answer. Network and temporary resource
recovery retain their established policies.

The token ledger has actual dispatcher usage and symmetric standalone-cache
attribution. The latter charges each arm once for every unique observation it
uses, so the second arm does not appear artificially cheap from shared requests.
Reliable tokens and conservative failed/unknown quantities stay separate.
Diagnostics have separate components. Test token/time metadata lives in its
own sidecar; scientific Test result records retain their exact prior schema.

Native callbacks record Parent/best/ties/frontier/frequency, correctness
complementarity with existing type/level metadata, child conversion and its
evaluation/token cost. Ledger-prefix replay verifies the recorded token cost
and archive availability. Native budget and token curves cannot backfill a
future candidate. Five scientific figures are exported as SVG and PNG; mock
figures, when provided, are clearly labeled as engineering fixtures.

The independent content screen is fixed before evaluation and never filters,
reselects, edits or scores a candidate. It flags fixed-reference variants,
explicit constant outputs, possible lookup, instance IDs and solution fragments.
Flags require manual interpretation; nonmatches do not certify legitimacy.
Native results and content risks are separate outputs.

The export examples below contain **synthetic engineering data only**;
they are not V6 scientific results:

- [Validation vs native budget](mock_figures/validation_native.png)
- [Validation vs attributed search tokens](mock_figures/validation_tokens.png)
- [Sampling frontier vs budget](mock_figures/frontier_native.png)
- [Nonbest Parent exploration vs budget](mock_figures/nonbest_native.png)
- [New-best discoveries vs budget](mock_figures/discoveries_native.png)

SVG counterparts and input/output fingerprints are in
[the figure manifest](mock_figures/manifest.json).

## Limits and readiness

The local audit found four raw source files but no complete exposure inventory
covering optimization, human analysis, scorer repair and tuning. Therefore no
new confirmatory Test was certified or frozen. This does not prove every unused
row was exposed; it means freshness is unverified. Old Test300 cannot be renamed,
resplit or assigned new IDs to manufacture a new held-out set. A genuinely new
set requires reviewed provenance and a separate frozen membership contract.

Historical exploratory Test remains possible only in a later explicit exact
authorization after all six searches close and pass audit. Nothing in this
preparation grants model access. Three fixed-seed stochastic repeats cannot
establish broad stability merely because their mean is positive. Token-aligned
Validation prefixes are not extra Test evaluations or equal-FLOP evidence.

Verification status and counts are recorded in the linked receipts. The first
complete attempt caught an incompatible extension of stable Test result fields;
the fix moved metrics to a sidecar while retaining strict immutable-result
comparison. Initial failure evidence is retained privately. Final readiness
must use the completed current-source receipt, not that failed attempt or the
earlier296-test V5 receipt.
