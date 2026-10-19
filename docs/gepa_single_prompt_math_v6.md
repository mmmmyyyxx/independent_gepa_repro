# GEPA V6 native selector comparison protocol

Status: offline engineering only. The 2026-10-19 task prohibits model API calls,
automatic execution, commits, pushes and reuse of historical authorization.
READY_TO_RUN remains false until current offline gates, committed source freeze,
exact dataset/phase/budget authorization and startup identity checks are complete.

V6 supersedes the current single-Prompt default entrypoint, not V5 measurements.
Historical V4/V5 configs, reports, memberships, scores and checkpoints remain
unchanged; historical execution/replay uses the original frozen Git source.
`scripts/single_prompt_gepa.py` uses `configs/gepa_single_prompt_math_v6.yaml`.
The new schema rejects an old frozen search identity rather than executing it.

## Scientific comparison

Official GEPA v0.1.1 is read-only at
`b4dbb55b7601dac448cdb836d5a401ca7d9eb920`. Both arms invoke `gepa.optimize`.
Only `candidate_selection_strategy` changes: native `current_best` versus native
`pareto`. Instance frontier, default reflection template, native sampler/shared
API RNG, per-Parent round-robin component rotation, minibatch3, skip-perfect,
strict local improvement, full Validation and native archive/best_candidate are
preserved. Merge is false; native evaluation cache is false. Locally improving
but globally worse/tied candidates still enter the archive. Current-best uses
the first aggregate maximum; equal scores do not replace its active Parent.

Role/Strategy/Answer are three editable strings in one Solver call. No content,
length, nonempty, no-op or answer-copy guard is introduced. The upstream selector,
reflection, component selection and archive implementations are not reimplemented.
No Gradient, Pattern, Memory, peers or team feedback enter either arm.

Each arm has repeats1/2/3, all optimizer seed42; these are stochastic provider
repeats at one fixed optimizer seed. The source bundle preserves Optimize150,
Validation100 and initialization exactly, without resampling. Its historical
Test300 stays exploratory. Different selectors consume shared RNG differently;
there is no custom paired-minibatch override. Reflection sees Optimize-only
task input, current output/parse/correctness, reference result and the same
4096-character worked-reference view. Validation never enters reflection.

Models remain the bundle's OpenLux gpt-4o-mini Solver and lwj qwen3.7-flash
Reflection. Solver temperature0.2/top_p0.8/presence0/frequency0, first3600 output
tokens and truncation6144; Reflection temperature0.7/top_p0.8/top_k20/presence1.5/
frequency0/nonthinking/max1800. Solver search concurrency32, Test16; Reflection1.
There is no added provider seed, model fallback or changed context contract.

## Native budget and stopping

Each arm/repeat has at most3000 native logical task-example evaluations. This
includes seed Validation100, Parent trace minibatches, child minibatches and
every complete Full Validation. Resolved cache hits consume logical budget.
Initial and selected Optimize150 diagnostics, final Test, Reflection and
physical retries are separate accounting dimensions, never silently omitted
from total search or evaluation costs.

Before entering an iteration, an outcome-blind reserve must fit the complete
worst case: Parent3 + child3 + Full100 =106. If not, stop normally before Parent
selection or Reflection. Every adapter evaluation additionally atomically admits
its entire batch before any dispatch or cache access. A batch violating the
reservation invariant is a genuine protocol abort, not a rejected candidate,
partial evaluation, silent skip, invented score or ordinary budget stop.

Executed iterations therefore have unchanged native semantics. While reserve
fits, the wrapper checks counters but consumes no RNG and changes no decisions.
Remaining budget at normal closure is0-105; exact exhaustion and inability to
fit a complete iteration are distinct reasons. A1000-proposal safety cap cannot
bind before the3000-call cap under the current nonempty minibatch contract;
it is still explicit and audited. There is no20-round stop. Invalid setup that
cannot fit seed Validation fails before even the first diagnostic request.

Record admitted batches, native/adapter/external counters, cap, actual use,
utilization, unused budget, stop reason and wall time per cell. An operational
interruption persists partial evidence and aborts; it never authorizes rerun or
cross-process search resume. Paid-answer local recovery and exact request network
retries continue within the existing process and scope.

## Shared scoring and reliability

`V5_EXACT_SCORING_ALL_PHASES_V6` binds the exact V5 bounded-separation algorithm
and pinned fallback to Optimize, Validation, Test and independent replay.
The legacy V5 numerical policy identifies the unchanged mathematical algorithm;
it is not an execution grant. V6 explicitly expands its permitted call sites.
No phase, arm, observed efficacy, sample ID or hard-coded answer changes a grade.
Replaying the original5346 graded observations must preserve every result.
Unknown/unsupported certificates fall back; timeout is unresolved computation,
never false/invalid. Two timeouts at the120-second ceiling escalate for owner
diagnosis. Temporary OS resource failures and allowed network failures keep
their existing accounted, interruptible retries.

Network retries remain indefinite for connection/timeout,408/409/425/429,500-599
and malformed transient envelopes, with2/4/8/16/30/60-second backoff, Retry-After
and provider cooldown. They reuse the exact request and do not consume another
native logical evaluation. Solver semantic draws and Reflection truncation
draws remain bounded at4. Permanent auth/model/request or identity/data/ledger
failures retain evidence and fail closed. Tokens and failed attempts are uncapped.
Per-arm search successful responses plus inflight cap51600 safely covers Solver
and Reflection bounds; per-arm Test cap3600. No model-failure masking is allowed.

## Observation, access and release

Identical Solver observations share only within the same repeat, phase, split
and exact structured request identity across arms. Repeats remain isolated;
Reflection is always fresh. A new attempt has a new cache and authorization.
[Token accounting](gepa_single_prompt_compute_v6.md) distinguishes dispatcher
usage and standalone attributed usage. No monetary costs are calculated, per the
user's explicit update. Always label: **Matched solver-evaluation budget, not
exactly matched total compute.**

Callbacks record Parent identity/first best, ties versus strictly worse Parents,
both raw instance-frontier and native pruned sampling-frontier sizes, frequency,
shared/unique correctness and existing canonical type/level metadata. Missing
metadata is unavailable, never inferred. Child records include generated/local
survival/Full/new best, gains/losses/net against Parent and contemporaneous best,
and corresponding native evaluations/tokens. These are observational only and
must pass native RNG and ledger-prefix reconciliation.

All six searches close before Test. Frozen deterministic post-hoc standards in
`configs/gepa_single_prompt_posthoc_v6.yaml` inspect all generated/final candidates
without changing acceptance, ranking, budget or scores. Risk flags call for
independent manual interpretation, not automatic illegality certification.
Their criteria and results are sealed with the search audit before Test opens.

A fresh Test requires a reviewed complete exposure inventory covering optimizer
inputs, human analysis, scorer repair and method tuning, identity/content
exclusion from existing splits, and a frozen300-member artifact/hash. Unused
rows alone are insufficient proof. Without that evidence, explicitly report
fresh confirmatory evaluation unavailable and bind historical exploratory
Test300 only if the exact later authorization says so. Never rename/redivide the
old Test. No Test outcome may modify search, content standards, pricing/weights
or the selected native winner. A flagged winner is not silently replaced.

[Preregistered analysis](gepa_single_prompt_analysis_v6.md) fixes curve availability,
token alignment, paired statistics and conservative interpretation. Formal
execution needs fresh single-use V6 authorization covering the exact source,
config, budget, dataset contract, roles and phases. This task grants none.
