# V6 selector comparison completed with V7 Test scoring amendment

All six frozen winners have completed historical exploratory Test300. Final
integrity reconciliation passed, including independent replay of 18,060 resolved
observations, both 900-evaluation Test profiles, the request/token ledger and the
single paid terminal repair. No search or winner selection was rerun.

| Repeat | Strict Validation correct | Native Pareto correct | Pareto minus strict |
|---|---:|---:|---:|
| 1 | 227/300 | 220/300 | -7 |
| 2 | 224/300 | 229/300 | +5 |
| 3 | 227/300 | 222/300 | -5 |
| Mean accuracy | 75.33% | 74.56% | -0.78 percentage points |

Pareto wins/ties/losses are 1/0/2. The paired two-way repeat/item bootstrap's
descriptive 95% interval for the mean difference is [-4.33, +2.78] percentage
points. Three stochastic repeats all retain optimizer seed42; they are not three
independent optimizer seeds. These observations do not establish stable Pareto
superiority or a statistically significant difference.

## Scoring repair and evidence preservation

V6 attempt2 completed all six searches, then stopped on a paid Test observation
whose large fractional exponent exhausted local symbolic grading. V7 adds a
bounded exact lower-exponent separation certificate, with unchanged pinned
parsing and fallback semantics. The old V5 implementation is preserved.

Before provider access, all 17,459 existing scores replayed unchanged; one
previously unresolved paid response was graded locally. Four Test profiles were
reused, and only the two missing Pareto profiles acquired new Solver responses.
All 76,463 original parent files and the nine previously completed strict Test
result/prediction/accounting files remain byte-identical. No paid observation was
resampled. The Test-driven scoring amendment is disclosed: this is not a fresh
confirmatory evaluation.

The final audit has zero pending physical reservations and one explicitly
acknowledged paid terminal repair. Execution is complete and its two-hour monitor
is disabled. No automatic rerun or further API scope remains authorized.

## Search and resource accounting

| Arm | Repeat | Generated / native parseable | Child Full Validation | Native logical evaluations |
|---|---:|---:|---:|---:|
| Strict | 1 | 70/70 | 22 | 2,897 |
| Strict | 2 | 78/78 | 22 | 2,966 |
| Strict | 3 | 105/105 | 19 | 2,915 |
| Pareto | 1 | 74/74 | 22 | 2,909 |
| Pareto | 2 | 85/85 | 21 | 2,938 |
| Pareto | 3 | 81/81 | 22 | 2,999 |

The six searches consumed 17,624 of 18,000 permitted native logical evaluations.
The outcome-blind 106-evaluation iteration reserve explains unused capacity.
This matches Solver-evaluation budgets; total computation and tokens differ.
No extra semantic guard was applied, as authorized. Native parseability does
not certify semantic legitimacy. The frozen observation-only content review flags
the selected strict repeat3 and Pareto repeat1 for independent manual review;
neither was filtered, rescored or reselected, and unflagged candidates are also
not certified. Detailed counters and uncertainty appear in [summary.json](summary.json).

The continuation made **672 new successful Test/Solver requests**, consuming
**657,304 accounted tokens**, with zero new search/Reflection requests or
transient failures. V6 attempt2 plus this continuation totals **21,087 physical
attempts**, **21,078 successful responses**, and **31,529,459 accounted tokens**.
That token figure includes 88,148 conservative bounds for nine original network
failures, rather than exclusively observed provider usage. Continuation wall time
is 943.422 seconds, excluding original execution and the grading interruption.
The separate failed V6 startup's 32 responses/15,053 tokens are excluded from these
study totals. No monetary estimate was calculated.

## Frozen identities and checks

- Parent source: `61d42b82b87a4198764641e5b6875a44308b11e5`.
- V7 execution source: `00be3132b12e649b3ed43e3706b08ee0c7f520be`.
- Source inventory: `1e3a821138124de190ba46f87fd870334babe1b55d9107f772ad334241b2330c`.
- Continuation: `94d7f29041fbe3262d401751f117a3b3c93b58ee3d1bebbe80bcae83759ebaa2`.
- Bundle: `296f22ab723f9574c8e9794f4d7e17801058d16b7e5e40fc52589df5ef005d49`.
- Upstream GEPA: v0.1.1, `b4dbb55b7601dac448cdb836d5a401ca7d9eb920`, unchanged.

The complete offline acceptance passed **367 tests**, with two explicitly skipped
duplicate integration scenarios, production compilation and deterministic
governance/lifecycle checks under the offline network guard. This evidence is
reused for the unchanged execution source; no full suite was rerun merely to
write this results report. See [offline acceptance](../gepa_single_prompt_v7_preparation_20261020/README.md),
[import review](../gepa_single_prompt_v7_preparation_20261020/import_review.json),
[final integrity audit](integrity_audit.json) and [parent preservation](parent_preservation.json).

The five figures use frozen search observations and add no evaluations:
[Validation versus logical evaluations](figures/validation_native.svg),
[Validation versus tokens](figures/validation_tokens.svg),
[frontier size](figures/frontier_native.svg),
[nonbest parent selections](figures/nonbest_native.svg), and
[new-best discoveries](figures/discoveries_native.svg).
Their [manifest](figures/manifest.json) records input and output hashes.

**Decision:** execution and evidence integration are complete. Historical exposed
Test300, the Test-motivated scoring repair, unresolved content-review flags and
three fixed-seed stochastic repeats limit scientific claims. New runs require
their own protocol and authorization. The user authorized local commits only;
no push was performed.
