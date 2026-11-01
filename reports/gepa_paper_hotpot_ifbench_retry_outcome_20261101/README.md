# Recovery V4 retry outcome ? 2026-11-01

The authorized retry used frozen execution source
`987c1f85e96f94437acd02f62b7114d44c0dde7e`, verified on remote main before
execution. The dual-role Canary passed. IFBench then aborted on a confirmed
provider content-filter error. HotpotQA is queued in its separately frozen
single-task controller using the still-unused exact phase grant. At the captured
status, available RAM was below its unchanged 6 GiB admission threshold.
This report is a timestamped snapshot, not a claim of final HotpotQA completion.
See [status and evidence hashes](status.json).

| Phase | Status at capture | Logical examples started | Physical attempts | Saved responses | Reported tokens |
|---|---|---:|---:|---:|---:|
| New dual-role Canary | COMPLETE | 0 | 2 | 2 | 700 |
| IFBench search | ABORTED during initial Validation | 20 | 26 | 24 | 13,596 |
| HotpotQA search | WAITING_FOR_MEMORY | 0 | 0 | 0 | 0 |

Known reported usage is **14,296 tokens**. Two failed IFBench attempts have
unknown usage; it is not reported as zero. No optimizer update, baseline or
Test evaluation occurred. No IFBench model call is still active.

## Confirmed failure and recovery behavior

Both preserved error records contain HTTP **400**, `error.code=content_filter`
and `error.param=prompt`. This is a provider policy rejection of the prompt,
not a network timeout, rate limit or server-status retry. No same-request retry
was applied. Raw provider messages, request IDs, prompts and answers remain
private. This establishes the cause of the two new errors; the missing body and
status of the 45 historical errors remain unconfirmed.

The new first-fatal cancellation worked: 300 examples were submitted to the
native executor, only 20 began root evaluation, and 24 paid successful responses
were preserved. All 300 futures completed or were cancelled, with no pending
future at exit. The ledger records both failed attempts separately from scores.
The two-task controller preserved its ABORTED result and stopped dispatch.

## Remaining HotpotQA scope

HotpotQA's phase was never dispatched or consumed by that controller. A new
private single-task handoff schedules only that already-approved unused grant;
its preflight passed without API calls. This is separate from the aborted pair
stage. It reuses no failed IFBench scope and changes no model, source, scientific
budget, cache identity, memory reservation or retry rule. The same tested
production scheduler and phase runner are used. The private controller only
narrows the allowed task list and task/cache cardinality to one. Its exact
command, source, launcher and grant hashes are frozen in the handoff.

The existing one-hour idle resource deadline remains in force. A read-only
monitor captures status every two hours and on termination; it cannot restart
or modify the experiment. Controller heartbeats continue every ten seconds.
Content-filter handling for IFBench requires resolution of provider access or
an explicitly reviewed protocol change before any new search attempt. Dataset
rows and prompts were not modified to force completion. Original failure
records and scores remain unchanged.

This publication adds only sanitized outcome evidence and status links. It
reuses the [459-test repair verification](../gepa_paper_provider_recovery_20261101/checks.json)
and [authorized scope](../gepa_paper_hotpot_ifbench_retry_20261101/README.md);
no runtime source or executable settings changed after execution freeze.
