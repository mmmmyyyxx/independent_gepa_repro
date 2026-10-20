# Initial Prompt Test300 baseline: three independent repeat scopes

The original Prompt is unchanged in all three repeats. Repeat2 reuses the latest
audited exact-initial-prompt Test profile: GEPA-CurrentBest repeat2 selected
candidate index0 and its Role/Strategy/Answer bytes equal the original initial
Prompt. It scored224/300. The reuse rule depends on identity and integrity, not
Test performance. Repeats1 and3 acquire fresh provider realizations with isolated
request/cache identities. No responses are shared between baseline repeats.

| Group | Repeat1 | Repeat2 | Repeat3 | Mean Test accuracy | Difference from baseline (pp) |
|---|---:|---:|---:|---:|---:|
| Initial Prompt baseline | 231/300 | 224/300 | 225/300 | 75.56% | +0.00 |
| GEPA-CurrentBest | 227/300 | 224/300 | 227/300 | 75.33% | -0.22 |
| GEPA-Pareto | 220/300 | 229/300 | 222/300 | 74.56% | -1.00 |
| C0 | 220/300 | 231/300 | 227/300 | 75.33% | -0.22 |
| C1 | 216/300 | 223/300 | 229/300 | 74.22% | -1.33 |
| C2 | 220/300 | 232/300 | 230/300 | 75.78% | +0.22 |

All Test denominators are300. Repeat numbers across methods do not imply paired
provider randomness. In particular, baseline repeat2 and GEPA-CurrentBest repeat2
are the same paid observation; they must not be treated as independent samples.
The baseline sample standard deviation is 1.26
percentage points. These fixed-seed stochastic repeats give descriptive estimates,
not a significance or stable superiority claim.

## Execution and verification

The authorized scope is Test/Solver only: initial Prompt, existing frozen Test300,
GPT-4o Mini and the original decoding/capacity/invalid-recovery policy. Production
search/scoring code is unchanged. V7 grades all new observations; the reused
profile already passed the V7 independent full-run audit. The private orchestration
script and its audit are hashed separately in the frozen scope.

New logical evaluations:600. New physical requests:634.
New successful responses:634.
New accounted tokens:434,655. The imported profile adds zero
new calls and retains its previous 223,982 accounted tokens
as provenance, without charging them again. There are no search or Reflection
calls. Transient network failures use unchanged accounted retries; invalid outputs
use at most four semantic draws and the first valid answer stops recovery.
No correctness-driven retry or provider seed parameter is introduced.

The independent final audit and a fresh-process replay pass all600 new observations, exact model/messages,
repeat-specific keys, first-valid recovery, paid-response and score replay, ledger
hashes, token charges, profile arithmetic and zero pending requests. Reused source
files remain byte-identical; all300 imported grades also replay unchanged in the
fresh process. Before execution, a network-blocked600-observation
fake lifecycle passed network/length recovery, repeat isolation, scope checks and
request/result tamper rejection. The unchanged execution source reuses its367-pass,
2-skip full offline receipt; it was not rerun solely for this baseline wrapper.

Source: `df19bf84ddfe093f0b0c4475293d4fd7026f7cb9`.
Execution identity: `7dd4c3eed642a517615ab07f448775e884b48c82a7acdb11b6a1e8ecc383fabb`.
Initial Prompt hash: `533ac46a1fd8418e7e9ca3d8995fa82c16d0e5685aac57986b7b26e8a086a526`.

## Comparison limits

Initial Prompt, Optimize150, Test300 and model decoding match across methods.
GEPA and the C0/C1/C2 study use different Validation100 memberships (37 common
items), evaluation budgets and candidate filters; the grader implementations and
concurrency histories also differ. Shared baseline scores do not remove those
confounders. Historical exposed Test300 and its scoring-repair history support
exploratory comparison only; these results never feed back into search or selection.

See [summary](summary.json), [integrity audit](integrity_audit.json), [fresh-process replay](external_final_audit.json),
[reuse review](reuse_review.json), [offline checks](offline_checks.json) and the
[original GEPA results](../gepa_single_prompt_v7_test_results_20261020/README.md).
Execution is complete; no automatic rerun or push is authorized by this task.
