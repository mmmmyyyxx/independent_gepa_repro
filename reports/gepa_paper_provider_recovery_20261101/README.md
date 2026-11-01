# Provider recovery repair ? 2026-11-01

Offline repair is complete. No model API calls, new Git commits or pushes were
made. Current tests: **459 passed, 18 deselected**; four retired historical
scoring modules remain excluded. The three warnings come from preserved
Hendrycks helper escape sequences. The focused subset has **89 passes**.
Verification ran in an isolated worktree at the recorded parent plus this repair.
The paper-suite runtime/config/test hashes now match the main workspace; 85
unrelated user files and both status-document bodies were preserved. Those
unrelated changes were not retested or certified by this task. The original
published worktree and all 75 frozen source files remain unchanged.
All six verification commands recorded zero network attempts with credentials
removed; production compile, fake native lifecycle, supervised concurrency and
fresh V4 launch preflight passed. See [checks](checks.json),
[preflight](preflight.json), [lifecycle](lifecycle.json) and
[concurrency](concurrency.json).

## What the error means

The [official OpenLux Chat API](https://doc.openlux.ai/en/reference/v1?leaf=232421919&op=post-v1-chat-completions)
defines HTTP 400 as a bad request or validation failure. The pinned LiteLLM
source can map both HTTP 400 and 422 to `BadRequestError`. The class alone
therefore cannot establish the actual status or cause. The official public
spec does not advise blindly retrying arbitrary 400 responses.
[Source provenance](sources.json) records the downloaded spec's hash.

The failed IFBench run recorded 45 such exceptions without their actual HTTP
status or provider body. Their root cause remains unconfirmed. Its 518 saved
responses, 410,329 reported tokens and unknown failed-attempt usage remain
historical evidence; this repair neither relabels nor reruns that attempt.

## Effective changes

- `provider_errors.py` extracts authoritative HTTP status across SDK wrappers,
  bounded cause chains, provider codes and Retry-After headers. It redacts keys,
  URLs and Bearer credentials from private diagnostic records.
- `control.py` retries 408/409/429, all 5xx and recognized network failures
  at most eight times, with the same request. Server delay and phase deadlines
  bound waiting. Other request/access errors, certificate errors and unknown
  failures halt with preserved diagnostics; they never become answer scores.
- `execution.py` stops paid dispatch and cancels queued work on the first fatal
  failure while draining, saving and metering responses already in flight.
  A 300-item regression verifies that queued calls do not continue dispatching.
- `scheduling.py` rejects an out-of-workspace handshake directory before spawn,
  and reports an explicit reason when a child exits without its handshake.
  `concurrency_check.py` verifies the real supervised process paths.
- V2 execution policy and V4 config/manifest bind these operational changes.
  The author search, Pareto selection, models, decoding, data, scoring and
  budgets are unchanged. Prior V3 configuration and evidence are preserved.

The native smoke also confirmed tail-duplicate winner semantics, concurrent
cache misses, paid late-response accounting and child/orphan cleanup. Full-index
mmap parity: 5,233,330 documents, 12 cases, zero bitwise differences. Preflight
verified 2,852 data rows, 146 dependencies and frozen author source checkouts.
The dedicated recovery tests also cover malformed/absent status, causal cycles,
server delays, exhausted retries and failed diagnostic persistence.

## Execution status

**HOLD for real API execution.** V4 is not a frozen clean committed source and
has no approved new Canary/search grant. The old failed IFBench scope cannot
be reused. The readiness record verifies offline work only. Fresh source freeze
and exact authorization are required by repository execution governance before
any new call. No experiment or baseline/Test evaluation was started.

See the [normative recovery contract](../../docs/gepa_paper_provider_recovery_v4.md)
and [V4 readiness](../../experiments/protocols/gepa_paper_five_tasks_openlux_qwen37_recovery_windows_v4/readiness.json).
