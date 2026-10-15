# Single-Prompt GEPA infrastructure recovery amendment V3

Current recovery is carried into V4. The [V4 candidate-policy amendment](gepa_single_prompt_native_guard_v4.md)
supersedes earlier candidate guards and defines exhausted Reflection generation
as native no-proposal rather than an empty synthetic candidate.

Status: OFFLINE PREPARATION; no formal model execution authorized.
This amendment implements the user's request to retry recoverable operational
failures. It supersedes the V2 recovery scope before any real experiment. The
experiment/config/frozen identities are V3; V2 review receipts remain immutable
historical offline evidence, not current readiness certificates.

Both arms use identical recovery. No GEPA selection, mutation, minibatch gate,
archive, feedback, score formula, model, decoding, memberships, repeats, seed or
search opportunity limit changes. This is an explicit common operational
amendment relative to the C reference, not a claim of identical failure handling.

| Failure | Disposition |
|---|---|
| SDK request timeout; DNS/TLS/connection drop surfaced as APIConnectionError | Retry exact request indefinitely |
| HTTP408/409/425/429; HTTP500-599 | Retry exact request indefinitely |
| Successful HTTP response with malformed JSON or incomplete transport envelope | Persist private evidence; retry exact request |
| Explicit authentication, permission, unknown-model or invalid-request failure | Stop with evidence; no silent fallback |
| Local payload extraction or mathematical scoring subprocess timeout | Retry same paid answer in every split and audit |
| Typed temporary worker launch/resource exhaustion | Retry same local computation |
| Completed valid wrong answer or completed invalid payload | Existing first-valid/four-semantic-draw policy |
| Prompt/data/source/authorization/ledger/control violation; unknown code failure | Stop with evidence |

Every provider attempt has its own reservation, failure/response receipt and
charge, stable transport-call identity and attempt index. Retries do not consume
model semantic draws, GEPA proposals or new logical evaluations. Missing usage
charges the conservative reservation. Failed attempts remain separate from the
existing successful-response plus in-flight ceiling. No retry count or token
ceiling is introduced. SDK retries remain0 so no physical attempt is hidden.

Backoff is2/4/8/16/30/60 then60 seconds. Respect valid Retry-After seconds,
retry-after-ms or HTTP-date by waiting at least the larger of the header and
backoff. A shared provider-profile cooldown prevents other queued workers from
immediately redispatching into the same outage; independent providers remain
separate. Waiting polls the user STOP marker, source/Test barriers and failure
state, with a30-second progress heartbeat. No search RNG is consumed by retries.

Normal local deadlines remain8 seconds during search and30 during Test. Retry
only typed timeouts and typed temporary resource failures. Double the local
worker allowance on retry up to120 seconds, then keep retrying at120; same
algorithm, same already-paid answer, no regenerated answer and no extra API
charge. Extraction must use this deadline too: the previous payload helper
turned subprocess timeout into PAYLOAD_PARSE_FAILURE and cached it. The V3
helper raises a typed infrastructure timeout instead and caches only completed
parser results. A completed native PAYLOAD_PARSE_FAILURE remains model-invalid.
The pinned parser/worker algorithms and ordinary successful outputs are unchanged.

Local scoring/parse retries are journaled separately from provider attempts.
Independent pre-Test and final receipt replay uses the same local recovery and
records its own recovery journal without altering the original provider ledger.
No automatic process restart, checkpoint resume, fresh experiment rerun or
scientific parameter adaptation is authorized. A killed process or damaged ledger
cannot be treated as a network retry. Formal calls still require the user's
fresh exact post-review authorization and committed source freeze.
