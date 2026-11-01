# HotpotQA / IFBench retry authorization ? 2026-11-01

The user explicitly authorized publishing the provider-recovery repair and
retrying execution. The scope is a fresh dual-role Canary followed by exactly
HotpotQA and IFBench search; no other task search, baseline or Test is included.
Prior failed scopes, raw responses and ledgers are preserved and not resumed.

Solver: OpenLux `openai/gpt-4.1-mini`; reflection: LWJ `openai/qwen3.7-flash`.
Both retain temperature 1, max_tokens 16384, seed 0 and one author-script repeat.
The author engine uses native Pareto selection without Merge; fixed data
memberships, scoring and the all-five-task barrier before Test remain unchanged.
The recovery V4 configuration and V2 execution profile are unchanged from the
[verified repair](../gepa_paper_provider_recovery_20261101/README.md).

| Phase | Native search threshold | Logical safety ceiling | Physical-attempt ceiling | Wall-time ceiling |
|---|---:|---:|---:|---:|
| Dual-model Canary | n/a | 1 | 18 | 3,000 s |
| HotpotQA search | 6,871 | 14,354 | 1,162,674 | 259,200 s |
| IFBench search | 3,593 | 7,798 | 350,910 | 259,200 s |

Operational ceilings abort rather than define scientific completion. Tokens
are recorded without a hard token ceiling, as previously selected. Retries
remain bounded at eight and do not permit a changed request or model fallback.
The frozen scheduler permits one retrieval and one nonretrieval child, subject
to its existing memory reservations and one-hour idle resource deadline.
Fatal child failure aborts the stage and preserves evidence.

The 459 current tests (18 historical cases deselected; four retired scoring
modules excluded), production compile, native fake lifecycle/concurrency smoke
and V4 data/environment/index preflight are reused because their covered
runtime, configuration and test bytes are unchanged. These were run with
credentials removed and zero network attempts. Before any new model call,
execution must verify the clean committed source, data/config/index/environment
hashes and a new exact single-use phase grant. Source, deployment, cache and
Canary bindings live in ignored private handoffs; this publication is not an
executable authorization template. At publication, execution has not started.
