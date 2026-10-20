# V6 attempt1 startup failure and path-only recovery

The user authorized execution after acceptance. Attempt1 started from the clean
61d42b8 source with a fresh single-use authorization, then aborted during the
initial Optimize diagnostic before native GEPA search, Reflection or Test.
It completed32 Solver responses and consumed15053 tokens:3802 input and11251
output. No physical request remains unresolved. The terminal monitor preserved
an alert and disabled its own future checks. No automatic restart occurred.

[Postmortem](postmortem.json) records the diagnosis and counters.
[Execution registration](../../experiments/protocols/gepa_single_prompt_math_v6/attempt1_execution_request.json)
preserves the consumed attempt identity and authorization. All raw receipts,
ledger events and checkpoints remain private and unchanged.

## Diagnosis

The deep execution checkout combined with the long run directory caused the
atomic paid-answer writer to open a265-character temporary path. A synthetic
same-length write reproduces FileNotFoundError on this host. All32 already-paid
responses pass response validation; an offline parser replay gives31 valid and
one model-invalid result, with zero operational parser failures and no new API
calls. No resolved answer or grade had been persisted before the abort.

The terminal category EXPERIMENT_STOPPED is a secondary shared cancellation
signal. It masked the first worker exception. The filesystem cause is diagnosed
from the paid-output replay, missing next artifact, deterministic writer path and
an actual filesystem reproduction; it is not presented as an originally logged
primary traceback.

## Prepared correction

A fresh shorter checkout and output directory preserve source61d42b8 and source
inventorydb31a411 exactly. Their production preflight and pinned imports pass.
Seventy-one synthetic write/atomic-replace/read probes cover the expected cache,
paid-answer and per-cell/native artifacts. The maximum checked proposed atomic
path is174 characters. This changes host placement only; no algorithm, score,
seed, data member, selector, budget, retry or candidate policy changes.

[Attempt2 plan](attempt2_execution_plan.json) and
[authorization request](attempt2_authorization_request.json) are concrete review
artifacts. They retain two selectors, three repeats each, seed42,3000 native
logical evaluations per cell, historical exploratory Test300, and uncapped token
and transient retry counts. The336-test receipt is reused only after exact
source-inventory equality. Prior paid caches and checkpoints are not reused.

## Authorization boundary

READY_TO_RUN=false for attempt2. The exact attempt1 authorization has already
been consumed. The frozen configuration sets automatic_rerun:denied and
resume:denied; production execution rejects both consumed scopes and existing
attempt paths. A new attempt therefore requires a new explicit user grant.
The attempt2 request has execute=false and no execution grant. No attempt2 API
calls, formal freeze or authorization consumption has occurred.

No new commit or push is included in this task. The original acceptance reports
and unrelated capacity-probe files remain preserved.
