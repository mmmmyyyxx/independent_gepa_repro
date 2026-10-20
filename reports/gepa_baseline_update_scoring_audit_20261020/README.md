# Baseline, actual GEPA updates and scoring-version audit

Baseline scored231/224/225 on historical exploratory Test300 (75.56%).
GEPA-CurrentBest scored227/224/227 (75.33%); GEPA-Pareto220/229/222 (74.56%).
The aggregate differences are two and nine correct observations per900, respectively.
There are three fixed-seed stochastic repeats; the baseline repeat2 is literally
the same paid profile as CurrentBest repeat2. Repeat numbers across methods do not
imply shared provider realizations. These means do not establish a true population
ordering or causally diagnose a search mechanism.

## Actual updates

| Arm | Repeat | Generated | Child Full Validation | Strict global-best refreshes | Validation correct /100 | Test correct |
|---|---:|---:|---:|---:|---:|---:|
| strict_validation | 1 | 70 | 22 | 2 | 71 -> 80 | 227/300 |
| strict_validation | 2 | 78 | 22 | 0 | 80 -> 80 | 224/300 |
| strict_validation | 3 | 105 | 19 | 3 | 72 -> 80 | 227/300 |
| native_pareto | 1 | 74 | 22 | 4 | 71 -> 82 | 220/300 |
| native_pareto | 2 | 85 | 21 | 1 | 80 -> 82 | 229/300 |
| native_pareto | 3 | 81 | 22 | 3 | 72 -> 79 | 222/300 |

The refresh count is computed independently from the ordered complete native
Validation-score archive and agrees with frozen mechanism telemetry. Full
Validation admission is not equivalent to refreshing the global best. CurrentBest
repeat2 generated78 candidates and evaluated22 children; none beat its initial80/100.
Native first-maximum tie handling returned index0, whose three block bytes equal
the initial Prompt. All six native searches start from the exact same Prompt.
Both selectors retain native minibatch strict-improvement screening.

Initial Validation scores71/80/72 vary between repeats despite identical initial
Prompt and memberships. Exact-request caching freezes observations within a repeat;
different repeats have fresh model observations. The two arms share eligible exact
requests within each repeat. Validation improves, but these Test results provide
no observed average generalization gain over this baseline.

## Cross-version scoring check

The original searches bind V5; V7 adds the previously disclosed bounded fractional
exponent certificate for completing Test. Baseline uses that same V7 scorer.
The V5 numerical implementation, worker, certificate, parser, invalidity resolver
and pinned mathematical worker remain byte-identical to source61d42b8; hashes are
recorded in [audit.json](audit.json).

Fresh offline replay covers all2,400 unique Test observations across baseline and
six GEPA final profiles, deduplicating the shared300-observation repeat2. There
are527 distinct reference/parsed-answer pairs. V7 reproduces all2,400 recorded
grades with zero changes. V5 resolves2,399, also with zero changed grades or
cross-version verdict disagreements. Its only unresolved computation is the exact
previously stalled Pareto repeat1 observation; V7 grades it false. The timeout is
missing computation, never an incorrect V5 verdict, and the repair adds no correct
answer to the numerator. All900 baseline grades reproduce under both versions.
The prior pre-continuation replay separately preserved all17,459 existing scores.
No scoring-version inflation of baseline is observed in these measurements.

## Output and instruction observations

Baseline has14/900 terminal invalid outputs; CurrentBest23/900 and Pareto27/900.
Counts include the original first-valid, maximum-four-draw recovery. Malformed
final boundaries and ambiguous payloads account for most invalid outputs. These
are model-output failures under the unchanged extraction rules, not evidence that
the parser changed between the cohorts. Accuracy conditional on validity is a
descriptive selected subset, not evidence of improved mathematical capability.

Some optimized blocks contain duplicated whole-Prompt instructions and block-like
headings. The largest selected Prompt has5,180 block-content characters versus309
initially (excluding rendering separators). This is legal under the authorized
native-only candidate policy. Redundancy and stronger step-by-step instructions
could affect generation or formatting, but this audit does not prove that they
caused Test losses or constitute a runtime bug. Two earlier automatic content
flags remain uncertified; no candidate was filtered, rescored or reselected.

Interpretation: finite Validation selection, provider variability and observed
output-invalidity increases are plausible explanations to investigate. No controlled
experiment here separates them. No method settings, Prompt, candidate selection,
test membership, scoring source or historical evidence were changed by this audit.
All checks use blocked outgoing sockets and zero new model calls.

See the [completed baseline and six-group table](../initial_prompt_test300_baseline_repeat3_20261020/README.md)
and [original GEPA result](../gepa_single_prompt_v7_test_results_20261020/README.md).
