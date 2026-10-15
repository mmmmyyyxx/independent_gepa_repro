# Native candidate policy amendment V4

The user's latest explicit instruction supersedes the earlier decision to retain
reference guards. Remove reference semantic/copy/dependency filters,3000-character
candidate limits, nonempty text checks and no-op rejection from BOTH arms.

Pinned GEPA v0.1.1 contains no independent semantic or answer-copy candidate guard.
Its native checks are seed/template/data contracts, native instruction extraction,
component updates, strict local improvement and full Validation/Pareto selection.
Calling these an anti-copy or generalization guard would be incorrect.

Keep3 string components so the task adapter can render the shared initial prompt;
empty strings, unchanged instructions and arbitrarily long text within actual
model limits are allowed. Scoring, models, frozen memberships, seeds/repeats,
resource ceilings, recovery, Test barriers and API/source/accounting checks stay
in force. These operational boundaries are not reference candidate guards.

Remove reference constraints from reflection feedback too. Keep the native meta
prompt and task feedback without adding instructions to avoid copying or fit an
artificial character budget. Candidate registration is provenance-only and
automatic. No semantic reviewer sits between generated text and Solver evaluation.

A completed empty native instruction is a real candidate. Four exhausted truncated
Reflection draws have not produced a completed instruction; their typed ordinary
exception follows the unmodified native no-proposal path and consumes that native
opportunity, with all paid attempts recorded. It does not fabricate an empty child,
score a legality failure or stop the whole experiment.

Completed provider JSON with explicit content:null is retained as an empty model
output, not an indefinitely retried transport failure. Solver's existing semantic
recovery handles empty output; completed empty reflection stays a native candidate.
A content-filtered Reflection uses native no-proposal rather than aborting the run.
Malformed transport envelopes and genuine provider/control failures retain the
separate retry/fail-closed rules.

Reports use native_parseable, native_accepted and full_validation_evaluated, with
semantic_guard_evaluated=false and guard_zero_metrics=0. They must not rename
native acceptance to contract-valid, leakage-free or generalized improvement.
V4 is a fresh protocol/config/frozen identity; V2/V3 evidence stays historical.
Formal model calls still require the user's fresh post-review authorization.
