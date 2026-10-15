# GEPA single-Prompt selector comparison V4

Status: OFFLINE PREPARATION. No formal model execution is authorized. V4 follows
explicit user instructions to remove ALL reference candidate guards, character
limits, nonempty-block requirements and no-op rejections. See the normative
[native-guard amendment](gepa_single_prompt_native_guard_v4.md).
The [paper/source review](gepa_single_prompt_semantic_review_v2.md) covers core
search semantics. Historical V2/V3 receipts do not certify this new identity.

Both arms use official GEPA v0.1.1 at
b4dbb55b7601dac448cdb836d5a401ca7d9eb920, read-only. They call the same
gepa.optimize and task adapter. The sole arm-dependent optimizer argument is
candidate_selection_strategy: current_best versus pareto. Both retain the native
archive, strict minibatch improvement gate, FullEvaluationPolicy, default
reflection template, epoch-shuffled sampler, API RNG wiring, per-candidate
round-robin component selection and final GEPAResult.best_candidate.
Merge is disabled in both arms: baseline GEPA, not the separate GEPA+Merge variant.

Strict current_best uses the first global Validation maximum. With fixed cached
binary outcomes on Validation100, changing the active parent requires at least
one additional correct item. Ties retain the incumbent. Locally surviving lower
or tied Validation candidates still enter the native archive; no extra global
admission gate or archive pruning is allowed. The native Pareto selector may
choose complementary candidates whose aggregate score is lower.

Each arm has3 repeats, all seed42, IDs1/2/3. Execution order is strict_validation
then native_pareto, sequential repeats. MaxCandidateProposalsStopper permits20
native opportunities per repeat. Perfect minibatches and native no-proposal
returns may yield fewer than20 generated candidates. Minibatch size is3. Equal
seed42 does not force identical samples: native selectors consume RNG differently.
No independent sampler RNG or paired minibatch override is introduced.

Initial Role/Strategy/Answer and exact Optimize150/Validation100/Test300 members
come from the frozen C-only V7 bundle. No data resampling occurs; original data
seeds20261001/88 remain provenance. System is role+two newlines+strategy+two
newlines+answer; User is the raw problem. These are3 editable text components in
one Solver call. Candidate values may be empty, unchanged or longer than3000
characters. Keys and string types are an adapter/wire interface, not a semantic
candidate guard. No reference candidate Guard runs, no candidate is assigned
zero by a legality filter, and no post-search semantic approval gates selection.

Reflection keeps the upstream template. Its Optimize-only feedback contains
problem, current components, ordinary model output, gold-blind parse status,
correctness, reference answer and the bounded4096-character worked-solution view.
There is no injected ban on copying, reusable-instruction admonition, length
budget or fixed response-style instruction. Validation/Test examples, labels and
individual outcomes never enter reflection. No Gradient, Pattern, Memory or team
feedback is imported. Native parsing/acceptance does not certify absence of
memorization or answer copying; final results must preserve that distinction.

Models and wires are unchanged: Solver OpenLux gpt-4o-mini, temperature0.2,
top_p0.8, frequency/presence0, max_tokens3600, truncation recovery6144. Reflection
lwj qwen3.7-flash, temperature0.7, top_p0.8, top_k20, presence1.5, frequency0,
enable_thinking=false, max_completion_tokens1800. SDK2.37.0 retries0, timeout120
seconds. Solver concurrency32 during search and16 during Test; Reflection1.
Nonthinking direct-zero/equivalent accepted-stop evidence remains required;
positive thinking metadata aborts, including discarded truncated responses.
Model context/input ceilings remain real provider/wire constraints, not a
candidate character-count gate.

Resolved Solver observations are shared only for the same repeat, phase, split,
structured candidate identity, example/reference and complete request. Different
repeats/phases are isolated; Reflection always calls fresh. Prompt registration
before cache access proves provenance only; it is automatic and never reviews
candidate semantics. Cache hits count as logical evaluations. The first dispatcher
pays physical cost; report both logical and physical costs and fixed arm order.
Initial and final Optimize150 diagnostics are charged but never select candidates.

The [V3 recovery rules](gepa_single_prompt_recovery_v3.md) carry into V4: indefinite
exact-request retries for request/connection failures, HTTP408/409/425/429,
HTTP500-599 and malformed provider envelopes. Backoff2/4/8/16/30/60 then60 seconds;
honor longer valid Retry-After seconds/ms/date, shared provider-profile cooldown,
interruptible waits and30-second heartbeat. Failed attempts receive conservative
charges and do not consume successful semantic draws or logical evaluations.
Permanent authentication/request/model failures, unknown code defects and genuine
source/data/authorization/ledger/control violations retain evidence and abort.

Solver permits4 semantic draws, first valid stops even if wrong. Local extraction
or scoring timeout/resource failures retry the SAME paid answer on every split
and audit. Deadlines start8 seconds during search and30 during Test, doubling to
120 for local retries. No local timeout becomes a cached model-invalid answer.
Reflection allows4 truncation draws with identical input. Exhaustion uses an
ordinary native no-proposal exception, not a fabricated empty instruction or an
experiment-wide abort. An actual completed empty instruction remains legal. Explicit content:null in a
completed response is an empty model output, not an infinite transport retry.
Content-filtered Reflection also uses native no-proposal; raw evidence is kept.

Resource ceilings remain PER ARM: training successful semantic responses plus
in-flight attempts <=90420; final Test <=3600. Tokens and failed physical attempts
are uncapped. Every attempt, receipt, role token count, resolved observation,
logical/native metric, generated proposal, native acceptance and final score is
retained and independently reconciled. Native-parseable count is not contract-valid
or anti-copy certification. Full-evaluated means complete native Validation,
excluding initialization. Iteration matching does not equal rollout/token matching.

All6 searches close and native final winners plus source/data/cache/scoring/ledger
replay pass before Test300 opens. Evaluate each of6 frozen final prompts once,
sharing identical Solver observations only within repeat. Test never selects or
revises prompts. Historical Test exposure limits confirmatory interpretation.
Shadow, team commits, automatic reruns and cross-process resume are forbidden.

Formal execution requires complete current offline gates, explicit user approval,
committed source/hash freeze, exact single-use roles/phases/budgets and startup
checks. No old grant, checkpoint or cache can authorize V4. No real call has run.
