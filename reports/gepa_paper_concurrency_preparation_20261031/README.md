# GEPA five-task concurrency preparation

Implemented and verified offline on 2026-10-31. **READY_TO_RUN=false**. No real
model APIs were called; model tokens consumed: 0. This is an execution amendment
to the [frozen scientific protocol](../../docs/gepa_paper_five_task_reproduction_qwen37_v2.md),
with parent source `32fc87e89d0bdc556959eabd86cebb949f15df56`.
No commit or push was performed for this task.

## Resulting execution

The [execution policy](../../configs/gepa_paper_execution_concurrency_v1.json) allows
one retrieval process plus one nonretrieval process. HoVer precedes HotpotQA in
the retrieval lane; IFBench and AIME fill the other lane; LiveBench runs alone.
Memory admission reserves 5GiB/1GiB/2GiB respectively plus 1GiB headroom, with
active-process future growth accounted for. Insufficient memory delays dispatch;
an idle stage aborts after one hour. These are planning reservations, not hard
memory caps. Existing phase wall/attempt ceilings remain finite safety ceilings.

The full BM25 index loads with mmap. Native search worker defaults (20 on this
host), 32-worker final evaluation, three-example minibatches, native 120-second
slow-tail resubmission, independent simultaneous cache misses and winner selection
are preserved. GEPA iterations and dependent retrieval hops remain sequential.
Windows process groups cover both venv launchers and their actual interpreters,
including descendants left after a parent exits.

All submitted futures finish before metering and transport are restored or a
successful receipt is sealed. Late paid responses are counted and persisted;
late fatal operational errors invalidate the phase. A failed child stops further
stage dispatch and terminates active child trees. Partial receipts and logs are
preserved; failures do not silently restart a consumed scope.

Every Test phase checks all five completed search receipts and frozen selections.
Selected-program Test additionally checks all five baseline receipts. Same-task
search, baseline and selected evaluation retain their bound cache namespace.
Models, prompts, data IDs/order, splits, seed0, author GEPA Pareto without Merge,
scoring, decoding, scientific budgets and retry rules are unchanged.

## Verification

| Check | Result |
|---|---|
| Current classified pytest suite, isolated task source | 417 passed; 18 deselected; 3 warnings |
| Historical coverage boundary | 4 existing retired-scoring modules excluded; not all historical replay |
| Production compileall under socket denial | Pass |
| Actual native executor with accelerated test clock | Tail duplicate still wins; all 3 physical calls metered and drained |
| Native concurrent identical cache misses | 2 distinct synthetic draws retained |
| Five fresh supervised synthetic processes | All complete; zero scores do not alter scheduling |
| Windows parent/descendant and orphan cleanup | Pass |
| Full 5,233,330-document mmap index, 2 query workers | 12 query/k cases; 0 bitwise score/document mismatches |
| Fake Canary ? search ? baseline ? selected Test lifecycle | Pass; 8 pre/post validation checks |
| Data/resources/environment preflight | 2,852 rows, 159 NLP files, 146 dependencies verified |
| Unapproved schedule through actual guarded CLI | Rejected before dispatch; zero socket attempts |

The tests use scrubbed credentials and a socket-denial guard inherited by spawned
Python processes. Synthetic authorization fixtures do not establish real source
freeze or API permission. Existing dataset and Windows-scoring parity evidence
is reused only where source/inputs are unchanged. Full-index file and corpus
hashes were rechecked. Earlier fixture-path, Windows venv-PID and editable-package
metadata issues were resolved before the final passing checks.

Evidence: [checks](checks.json), [native/process/index verification](concurrency.json),
[lifecycle](lifecycle.json), [preflight](preflight.json),
[source inventory](source_inventory.json), [preservation checks](preservation.json).
The full suite ran with the exact final runtime sources listed in the inventory;
unrelated local user modifications in the main worktree were excluded.

## Remaining execution conditions

The [operational amendment](../../docs/gepa_paper_concurrency_v1.md) and
[inactive preparation pack](../../experiments/preparations/gepa_paper_execution_concurrency_v1/readiness.json)
bind a new authorization-v2 schema and execution-policy hash. All templates remain
unapproved, with no frozen new source SHA. Existing source-32fc87e grants and
checkpoints cannot authorize this runtime. A clean committed task source, a fresh
exact-model canary and exact phase/stage authorization are required before calls.

No real throughput benchmark or provider RPM/TPM verification was performed.
Two process lanes can overlap independent work; the actual time saving depends
on free memory, provider limits and native sequential reflection/search work.
This change does not reduce the scientific evaluation budget or guarantee fewer
tokens. The previously published release and all historical evidence remain
unchanged. Main-worktree user edits are preserved.
