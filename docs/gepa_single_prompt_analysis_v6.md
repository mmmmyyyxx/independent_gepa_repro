# V6 preregistered result analysis template

Status: fixed before V6 model evaluation. No V6 result exists. No comparison
criterion may be changed in response to a future arm's efficacy.

## Required result record

- Source SHA and complete inventory hash; upstream SHA, config/protocol/policies.
- Optimize150/Validation100 and exact selected Test identities and hashes.
- Seed42 repeated three times per arm, explicitly not three different seeds.
- Native actual/cap/remaining/utilization/stop reason for all six cells.
- Native-parseable/generated/unique/local-surviving/Full/new-best counts.
- Initial and selected Optimize and Validation scores, final Test correctness,
  invalid counts and actual fixed denominators. No selective exclusion.
- Solver/Reflection input/output, unknown and failed bounds, successes, retries,
  physical requests, cache hits, both token attribution views and cell wall time.
- Native final hash, post-hoc content flags/manual interpretation, and no
  post-test replacement of a native winner.

## Five curves

Export data and standalone figures for (1) best Validation accuracy vs native
metric calls; (2) best Validation accuracy vs total attributed search tokens;
(3) native sampling-frontier size vs native budget, also recording raw instance
frontier size; (4) cumulative strictly-nonbest Parent selections vs budget;
(5) cumulative strict new aggregate-best discoveries vs budget, excluding seed.
All repeats are visible, not just the best run. No Test curves are used for
adaptive selection. Native milestone coordinates are500/1000/1500/2000/2500/3000.

When a Full batch crosses a checkpoint, only candidates archived before that
checkpoint are available. Do not evaluate to fill a point, use a partial Full,
backfill a future winner or allocate free evaluations to a larger frontier.
Record actual terminal spend alongside any unspent nominal budget. Token-prefix
and common-support rules are fixed in the compute specification. Mechanical
logging performs no Solver calls and consumes no search RNG.

## Pareto mechanism table

For each Parent selection, compare to the contemporaneous native first argmax.
Report separately strictly lower aggregate-score selections and alternative
equal-best selections. Denominator is all valid Parent selections, including
perfect-minibatch/no-proposal opportunities; also report the generated/Full
conditional funnel. Report distinct Parent count separately from repeated draws.

For lower-scoring Parents, compute shared correct, Parent-only and best-only
correctness from the already measured Validation matrix. Use existing canonical
type/level fields only; missing categories stay unavailable. Track each mutation's
native calls and token delta, local/Full outcome, child gains/losses/net relative
to Parent and current best, and strict new-best status. Count and cost
`Non-best Parent -> New Aggregate Best`. Realized lineages support activation of
the mechanism, not a counterfactual proof that greedy could never find that child.

## Paired generalization comparison

Report each repeat's two accuracies, Pareto-minus-current-best difference, mean
difference, sample standard deviation, Win/Tie/Loss, per-item corrected/regressed/
unchanged counts and invalid outcomes. Pair exact item IDs and order across arms
and repeats. Do not treat three runs over the same300 items as900 independent
problems. Identical final requests retain paired realizations where permitted.

A descriptive95% interval uses2000 paired two-way bootstrap draws, analysis RNG
seed42. Resample the three repeat indices jointly for both arms, and resample
item indices once per draw shared across all sampled repeats. This preserves
the common-item dependence instead of independently resampling900 rows. It
does not solve the severe uncertainty from three stochastic repeats at one
optimizer seed. No significance/stability declaration follows from the mean or
from this descriptive interval alone. The analysis RNG never enters search.

If a genuinely fresh frozen Test is supported by complete exposure provenance,
label that evidence separately. Otherwise historical Test300 is exploratory only;
no fresh held-out confirmation claim is allowed. Never tune a guard, scorer,
budget, seed or winner using final Test. If data eligibility remains unverified,
the primary fresh-confirmation question remains not evaluable.

## Independent content review

Freeze the same deterministic screening parameters and manual rubric for both
arms before final evaluation. Screen every generated and final candidate for
long training-reference literals and mathematical notation variants, short
answers in explicit sample context, reference-solution token fragments, instance
IDs and possible lookup constructions. Retain source hashes and evidence privately;
publish categories/counters, not texts or fixed answers. This does not change
the native acceptance rules. General mathematical techniques are distinguished
through independent manual review, not automatically rejected by lexical overlap.

Automatic matches are risk flags and nonmatches are not compliance certificates.
Report native raw results, content findings and resulting interpretation limits
separately. A reviewer may label generic technique, concrete training material,
identity-specific lookup or ambiguous. Do not silently reselect a more favorable
candidate or omit risky runs. A guarded follow-up requires a separate identity.

## Conclusion fields, all required

1. Was nonbest branch exploration activated, and did it produce new Validation bests?
2. Was Pareto better under the matched Solver cap, including actual budget use?
3. Was it better at common attributed search-token coordinates?
4. Were paired effects directionally consistent across all three repeats?
5. Does a genuinely fresh Test support generalization, or is this unavailable?
6. Do content findings constrain the claimed source of any improvement?

Use NOT_EVALUABLE/INSUFFICIENT_EVIDENCE when conditions are unmet. An unfavorable
valid result never justifies increasing the budget, changing seeds, rerunning or
altering interpretation rules. The purpose is an auditable comparison, not
ensuring a Pareto win.
