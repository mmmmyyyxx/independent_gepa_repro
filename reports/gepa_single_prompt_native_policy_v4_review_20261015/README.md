# GEPA native candidate policy: V4 offline review

The user's latest decision removes every extra candidate restriction from both
arms: reference semantic/copy/dependency filters, the3000-character limit,
nonempty-block checks and no-op rejection. Pinned GEPA v0.1.1 has no independent
semantic or answer-copy guard. Native acceptance cannot certify absence of answer
copying or generalization.

The current [protocol](../../docs/gepa_single_prompt_math_v1.md),
[native-policy amendment](../../docs/gepa_single_prompt_native_guard_v4.md),
[paper/source review](../../docs/gepa_single_prompt_semantic_review_v2.md) and
[V4 proposal](../../experiments/protocols/gepa_single_prompt_math_seed42_repeat3_v4/proposal.json)
define this preparation. Earlier V2/V3 reports and proposals are historical and
remain unchanged. No scientific performance result is claimed here.

Both arms call the same pinned native GEPA engine; the sole arm-dependent
optimizer argument is current_best versus pareto. The strict arm maintains one
active parent chain, switching only after Validation100 improves by at least one
correct item. Native archival history remains intact, including locally surviving
candidates that fail to improve aggregate Validation. Native minibatch survival,
reflection template, component rotation, sampler/RNG wiring, full validation and
final best-candidate selection are shared. Different selectors can consume RNG
differently even with identical seeds. Merge is disabled in both arms.

This review checked the [official paper](https://proceedings.iclr.cc/paper_files/paper/2026/file/0e9e708b6f48e14fd0ac29e167413f76-Paper-Conference.pdf)
against the pinned source and adapter. Shared models, three string components,
MATH feedback, observation pairing and operational recovery are task adaptations;
this is a selector comparison under that harness, rather than reproduction of
the paper's benchmark results.

| Boundary | Verified behavior |
|---|---|
| Previously filtered content | Generic math, fixed-answer, long, empty and unchanged candidates reach native handling without custom rejection |
| Candidate accounting | Native parseable/accepted/full-evaluated counts; semantic_guard_evaluated=false; no guard-zero scores |
| Exhausted truncated reflection | Four recorded draws, then native no-proposal path; no fabricated empty child or experiment abort |
| Completed empty reflection | Native candidate, including explicit provider content:null |
| Content-filtered reflection | Native no-proposal path |
| Completed empty Solver output | Existing bounded semantic recovery, separate from transport retries |
| Network/provider transient failures | Exact-request retries with durable receipts and shared provider cooldown |
| Local scorer timeout/resource pressure | Retry the same paid response, including Validation, Test and audit |
| Unchanged file bytes or packed Git refs | Metadata changes alone do not stop execution |
| Closed optional progress output | Recovery continues; durable evidence writes remain mandatory |

Network retries cover connection/timeouts,408/409/425/429,500-599 and malformed
provider envelopes. Backoff is2/4/8/16/30/60 seconds, remaining at60; valid
Retry-After seconds, milliseconds or HTTP dates can extend the wait. Transient
attempts have no count limit. Local workers start at8 seconds in search and30 in
Test, double to120, then retry at120. Thirty-second heartbeats check STOP and
frozen identity. No hidden SDK retry, fallback model, automatic rerun or resume
is introduced.

Permanent credential/request/model errors, actual source/data/accounting changes,
resource ceilings, lost durable evidence and unauthorized split access still stop
execution. Retrying those conditions would invalidate the frozen experiment.

Optimize150/Validation100/Test300 memberships remain unchanged. Both arms have
three repeats, seed42 and at most20 native opportunities per repeat. Exact Solver
observations are shared within repeat across arms and isolated across repeats;
Reflection is always fresh. Reference per-arm semantic/inflight ceilings remain
90420 search and3600 Test, with no token ceiling. Test follows closure, audit and
sealing of all six searches; historical Test exposure is disclosed.

The complete offline suite passed272 tests in518.16 seconds, including72
recovery-module checks. Production compileall, pinned environment/bundle
preflight, scoring/rendering parity, semantic and ledger checks, CLI smoke and
git diff --check passed.

The [complete offline receipt](offline_gates.json) and
[review record](native_policy_checks.json) bind the actual test count and source
inventory. All tests use fake providers or mocked HTTP, with environment
credentials removed and outgoing sockets blocked. The three complete six-cell
fixtures cover normal changes, fixed-answer candidates being measured without
improvement, and transient Solver/Reflection recovery. These are engineering
checks and do not estimate model performance. Sibling private historical replay
suites were not run.

Real model requests and model tokens:0. No source commit, push or formal grant
consumption occurred. READY_TO_RUN=false; HOLD pending user review, an explicitly
authorized committed source freeze and fresh exact formal API authorization.
