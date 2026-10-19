# GEPA expansion audit, 2026-10-19

The historical optimizer/selector implementation passes this offline mechanism audit. **An expanded real run is HOLD** until budget admission, complete scoring/recovery binding, instrumentation and a fresh freeze are implemented and verified. No model calls, experiment launch, commit or push occurred in this audit. The existing source and historical evidence were unchanged.

The user's latest instruction takes precedence over the attachment's multi-seed suggestion: keep seed **42**, keep three repeats per arm and existing data memberships. Use the expansion to supersede the active preparation/default entrypoint; preserve old frozen reports as historical evidence. This audit does not overwrite measured results or execute the proposed replacement.

## What Pareto actually did

All 120 historical iterations were replayed using the pinned native selectors and epoch-shuffled sampler with their original shared RNG. Both Parent indices and minibatch IDs matched exactly. Candidate hashes, pool prefixes, lineage and binary Validation100 matrices reconciled. The ledger hash chain was verified to the completed final-audit tip. This audit reused the prior full mathematical audit rather than rerunning 6,247 local grades.

| Mechanism measure | Strict current-best | Native Pareto |
|---|---:|---:|
| Parent selections, including perfect-minibatch skips | 60 | 60 |
| Parent strictly below the current best aggregate score | 0 | 28 (46.67%) |
| Parent differs from the native first argmax, including ties | 0 | 36 (60.00%) |
| Alternative equal-best selections | 0 | 8 |
| Generated candidates from strictly lower-scoring Parents | 0 | 15 |
| Full-evaluated children of those Parents | 0 | 9 |
| Strict new aggregate bests from those Parents | 0 | 2 |
| All native logical evaluations across three repeats | 1,673 | 1,982 |

Pareto therefore used 18.47% more native logical evaluations in the old experiment. Equal 20-opportunity limits did not yield a compute-matched comparison; the observed mean Test difference cannot establish greater budget efficiency.

Every one of the 28 below-best selections had some complementary Validation correctness: 1-5 items correct where the contemporaneous first-best Parent was wrong, averaging 3 items per selection. These are repeated selection events, not 28 distinct Parents or independent samples. Tied alternatives are reported separately rather than counted as strictly inferior Parents.

Two direct lineage witnesses exist:

| Pareto repeat | Iteration | Parent Validation | Best before mutation | Child Validation | Parent-only correct items |
|---|---:|---:|---:|---:|---:|
| 1 | 10 | 76/100 | 77/100 | 78/100 | 4 |
| 2 | 17 | 74/100 | 77/100 | 79/100 | 3 |

These demonstrate realized non-greedy branch exploration and two subsequent Validation improvements. They do not establish a counterfactual greedy failure, causal attribution to complementary items, a pure reasoning improvement, or stable Test superiority. The historical Test outcome remains one Pareto win, one tie and one loss, with a mean difference of +0.78 percentage points. The first witness is also subject to the content finding below.

## Selected-candidate content finding

I manually read all six selected final candidates. Pareto repeats **1 and 3** retain a concrete training reference result in explicit example/reference context; repeat 3 additionally retains example-level success/failure discussion and specific numeric outcomes. Long literal matches were confirmed against the Optimize150 source rows and the originating proposal's own reflection source IDs. The retained components originated at iteration 10 (generation 7 and 8 respectively). Private text and source expressions are not published.

The other four selected candidates showed no obvious direct fixed-reference copying in this manual review. This is not a certificate of legality or generalization; all 65 generated candidates were not manually certified. No retrospective filtering, reselection or score changes were made.

Training worked-solution feedback was explicitly allowed, and the frozen protocol used native-only candidate checks. Thus these observations do **not** establish a violation of that protocol, held-out leakage or causal inflation of Test scores. They do limit the claim that all gains came from reusable instruction changes. Keep the raw native outcome and an independent content-review label; do not silently add a generation Guard or select a new winner from Test outcomes. Historical artifacts remain intact.

## Expansion readiness findings

| Priority | Finding | Required treatment before a new real run |
|---|---|---|
| High | Native `MaxMetricCallsStopper` is checked between iterations. A synthetic threshold of 101 produced 206 logical evaluations. | Freeze a precise boundary policy. Recommended: reserve the worst-case complete iteration at the boundary and stop before starting when it cannot fit. |
| High | The default loader requires exactly 20 iterations, and the funnel audit requires exactly that count. Merely changing YAML or adding a second stopper either fails conformance or still stops at 20. | Replace the active opportunity cap and its loader/audit identities together with budget-driven termination. |
| High | V5's repaired scorer and finite computational-timeout escalation are scoped to the Test continuation. Ordinary `Runtime.score_prediction` and default `reconcile` still use the old scorer/recovery. | Give the expansion an explicit shared search/Validation/Test/audit scoring policy. Preserve pinned fallback and timeout-as-unresolved semantics. Do not reuse the Test-only continuation grant. |
| Medium | Current history is sufficient to reconstruct old Parents, but lacks direct complete-budget snapshots and complementary-coverage metrics. | Add observation-only snapshots and ancestry metrics; never feed them back to the optimizer or consume additional RNG. |
| Medium | The older README's generic metric-count warning does not describe this single-prompt path. | This pinned path counts Parent trace, child minibatch and full Validation evaluations. Reconcile adapter, native state and external logical ledger rather than assuming an omitted Parent count. |
| Medium | Fixed-seed repeats provide stochastic provider repeats rather than distinct optimizer-seed evidence. | Keep seed42 as instructed; label them accurately and use paired repeat results. Do not treat 900 repeated Test responses as 900 independent problems. |
| Medium | Test300 is historically exposed; candidate content has the finding above. | Keep exploratory interpretation and independent post-hoc content reporting. A new sealed Test would be a separate user decision, not part of this same-membership expansion. |

The exact old native accounting identity is `100 + 3*iterations + 3*generated + 100*new_full_candidates`. It matches every cell and the external ledger. Initial and selected Optimize150 diagnostics add 300 logical evaluations per cell, outside that native count. Resolved cache hits count; up to four semantic draws, transient physical retries, Reflection calls and tokens are separate cost dimensions.

## Reviewed replacement design, not executable authorization

The attachment recommends a range. For a concrete implementation target this review recommends **3,000 native logical task-example evaluations per arm per repeat**, with three repeats all seed42. This proposed target is not a newly frozen budget or authorization. Both arms retain the same settings, with only `candidate_selection_strategy` differing.

Keep official v0.1.1, instance frontier, three editable string components, default reflection template, worked-solution feedback, strict local minibatch survival, native archive, first-best final selection, full Validation100, minibatch3, native RNG/sampler/component rotation, Merge off, native-only candidate checks, models/decoding/concurrency and exact within-repeat Solver sharing. Shared requests count logically for both arms; first-dispatch physical cost is not a fair per-arm compute endpoint. Start with a fresh experiment identity/cache and single-use authorization; do not relabel or extend the old 20-round checkpoint.

For this exact no-merge/full-evaluation setup, one complete iteration costs at most **106** logical evaluations: Parent3 + child3 + Full100. An outcome-blind boundary reserve of 106 keeps executed iterations intact and guarantees no cap overrun; unused budget can be 0-105. Equal caps therefore do not guarantee identical realized usage. A synthetic 3,000-cap reserve run completed 27 full candidate additions using 2,962 evaluations. This is a budget-mechanics fixture, not a prediction of real candidate yield. Stop normally on budget exhaustion, never by treating an incomplete Full as a rejection or a timeout as a wrong answer.

The proposed six-cell search allowance is 18,000 native evaluations. Separately allow 1,800 Optimize diagnostic evaluations and 1,800 final Test evaluations, totaling at most **21,600 logical task-example evaluations** before semantic-draw multiplicity. Reflection and failed network retries are not included in this number; no hard token/currency upper bound follows from it. Derive and freeze the physical/semantic resource ceilings by role and phase, preserving the user's retry policy and no fallback.

Record an event curve when each complete Validation profile becomes available, plus 500/1000/1500/2000/2500/3000 milestones and actual terminal spend. A new candidate enters a curve only after its Full100 completes. No partial Full scores, future winner, or repeated Test access may enter a budget point. The old curves in the JSON use null for milestones beyond old termination rather than extrapolating a 20-round result to a larger budget. All six searches must close, audit and seal before the existing final Test phase opens.

The replacement needs one current schema/config/entrypoint and tests for pre-dispatch budget reservation, cache-hit logical cost, no retained 20-round stop, complete Full admission, prefix-only curves, observer RNG transparency, shared repaired scoring, transient retries and exact fresh scope enforcement. The historical runtime can be recovered from its frozen Git SHA; no compatibility execution mode is needed. Full current offline gates must pass for the resulting source before formal authorization and startup.

## Paper and source scope

The paper's Table3 compares selectors while holding the evolution harness fixed. Section E.4 uses minibatch3, distinguishes Merge, and matches per-benchmark rollout budgets rather than prescribing a universal 3,000-call budget. This MATH/provider/feedback interface is an independent evaluation of that mechanism, not a reproduction of its benchmark scores. [Paper, v2, Table3 and E.4](https://arxiv.org/pdf/2507.19457v2).

The official FAQ's 15-30 times validation-size guidance motivates the proposed scale; it is an experience-based recommendation, not a paper budget or a performance guarantee. Consulted on 2026-10-19. [Official FAQ](https://github.com/gepa-ai/gepa/blob/main/docs/docs/guides/faq.md).

Pinned source inspected: [optimizer boundary](https://github.com/gepa-ai/gepa/blob/b4dbb55b7601dac448cdb836d5a401ca7d9eb920/src/gepa/core/engine.py), [stop conditions](https://github.com/gepa-ai/gepa/blob/b4dbb55b7601dac448cdb836d5a401ca7d9eb920/src/gepa/utils/stop_condition.py), [native selectors](https://github.com/gepa-ai/gepa/blob/b4dbb55b7601dac448cdb836d5a401ca7d9eb920/src/gepa/strategies/candidate_selector.py), [trace and child accounting](https://github.com/gepa-ai/gepa/blob/b4dbb55b7601dac448cdb836d5a401ca7d9eb920/src/gepa/proposer/reflective_mutation/reflective_mutation.py).

Evidence: [mechanism audit](mechanism_audit.json), [non-executable expansion review](extension_review.json), [verification receipt](checks.json), [completed V5 result](../gepa_single_prompt_native_v5_results_20261016/README.md).

Verification scope: report/evidence audit, with no production/config changes. The prior 296-test offline receipt was reused only after source-inventory equality; it was not rerun. New checks were 120 native Parent/minibatch replays, ledger/hash and split reconciliation, six selected-candidate content reviews, five synthetic native-budget checks, links/arithmetic/sanitization and diff whitespace. Historical private replay tests were not run. Real model requests and tokens this task: **0**.
