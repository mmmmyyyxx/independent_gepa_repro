# Paper-suite provider recovery V4

This is the 2026-11-01 operational repair requested after the IFBench seed
Validation failure. The original IFBench attempt and its 518 paid responses,
45 failed attempts, 410329 reported tokens and original scores/ledgers remain
immutable. No new model calls are authorized or made by this repair.

## Official evidence and limits

The [OpenLux Chat API](https://doc.openlux.ai/en/reference/v1?leaf=232421919&op=post-v1-chat-completions)
defines 400 as a bad request or validation failure. Its `NewApiError` object
includes `error.message` and `error.type`; the message may include a request ID.
The [introduction](https://doc.openlux.ai/en) distinguishes authentication/model
access errors and points to platform error guidance. The public V1 OpenAPI
fetched during this audit has no `x-error-playbook`; it provides no blanket
instruction to retry arbitrary 400 errors. The pinned LiteLLM implementation can
map both 400 and 422 to `BadRequestError`, so the Python class is not an exact
HTTP-status record. These facts do not identify the missing body/status of the
45 historical failures. They cannot be reconstructed or retroactively relabeled.

The local ignored audit archive contains the fetched official spec and its
public-doc retrieval metadata. It contains no account-management access or model
requests. The repair does not change the configured private provider endpoint.

## Closed recovery rules

The [V2 execution profile](../configs/gepa_paper_execution_concurrency_v2.json)
and [V4 manifest](../experiments/protocols/gepa_paper_five_tasks_openlux_qwen37_recovery_windows_v4/manifest.json)
freeze the new recovery identity `paper_provider_http_recovery_v2`.

- HTTP status takes precedence over the SDK class: outer response status, outer
  exception status, then a bounded causal-chain search. Numeric string statuses
  normalize to integers. An explicit outer 400 is not overridden by an inner
  timeout or text that happens to mention 503.
- 408/409/429, all 5xx, and recognized timeout/connection/DNS/reset/EOF failures
  receive at most 8 retries of the same request. This retains 9 physical attempts
  at most per call, without consuming scientific RNG or changing request content.
  Certificate validation, unknown errors and request/access 4xx receive a diagnostic
  halt. Error-message keyword guesses do not turn 400 into a transient failure.
- Retry delay is the larger of exponential backoff and a valid `Retry-After`
  seconds/date or milliseconds header. It never retries earlier than the server
  delay. The phase wall deadline bounds waiting; a delay that cannot fit fails
  explicitly. Shared fatal cancellation interrupts backoff within 1 second.
- Before retry or halt, persist an atomic private evidence record containing HTTP
  status and provenance, error body/type/code/parameter, exception chain, request
  shape, and correlation hash. Redact credentials, Bearer strings and URLs. The
  private ledger contains only metadata and the evidence file's byte hash;
  messages/bodies never enter public reports or optimizer feedback.
- If error evidence cannot be saved, halt further dispatch. Failed-attempt usage
  remains unknown unless actually reported; it is never invented as zero.

## Fatal work and accounting

The first fatal transport/worker failure sets a shared dispatch halt. Subsequent
root evaluations and paid-request reservations cannot proceed. The first fatal
future callback cancels queued futures outside the registry lock; running HTTP
requests remain bounded by their existing timeout. Any paid in-flight response
is still persisted and metered before a receipt is sealed. The phase still
aborts: errors do not become wrong-answer scores or dataset omissions.

This corrects the waste observed when 300 submitted seed examples all continued
after the first fatal error. Successful healthy executions preserve the native
GEPA search, Pareto selection, minibatches, cache concurrency,tail resubmission,
first-result winner, models, decoding, data, scoring, seeds and native budgets.
The existing coordinator rule that a failed child aborts its stage is retained.

## Dispatch handshake

`ProcessJob` rejects an output/handshake directory outside the governed workspace
before opening logs or spawning a child. A child exiting before the handshake or
missing its startup deadline produces an explicit operational reason instead of
an incidental FileNotFoundError. The synthetic integration now covers these
paths alongside real parent/descendant/orphan cleanup.

## Freeze and next execution

V3 and earlier configs/manifests, failed scopes, caches and raw evidence are kept.
Only V4 is accepted by the current runtime. New grants must bind the changed
source, configuration and execution-policy hash. Existing positive grants and
the V3 Canary do not authorize V4. Templates/readiness remain false and unapproved;
no formal run or retry follows from this offline task. A fresh committed clean
source and exact new authorization are required before real execution.
