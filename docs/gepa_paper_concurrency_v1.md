# Five-task execution concurrency V1

This operational amendment accompanies the frozen scientific
[Qwen optimizer V2 protocol](gepa_paper_five_task_reproduction_qwen37_v2.md).
It preserves the author GEPA search, native Pareto without Merge, all prompts,
data IDs/order/repetition, scoring, models, decoding, search thresholds, cache
behavior, minibatch size and native worker defaults. It changes phase supervision,
resource loading and scheduling. It is not an API authorization.

## Policy and identity

[Execution policy](../configs/gepa_paper_execution_concurrency_v1.json) is a closed,
validated policy. Each new phase grant uses the scientific identity's
`_authorization_v2` schema and must bind `execution_policy_sha256`, the resolved
native `search_threads` and `final_eval_threads`. Runtime, cache identity, Canary
provenance, search provenance and final receipts carry the same bindings.
The old v1 phase grants cannot authorize this runtime. Do not edit or relabel
historical grants, checkpoints, frozen source or reports.

Search still resolves the author's `num_threads=None` with `os.cpu_count()`;
on the preparation host this is 20. Final evaluation remains 32 workers.
Three-example minibatches and within-program hop dependencies are unchanged.
No new single-flight cache, deduplication, altered winner rule or disabled
slow-tail resubmission is introduced. Provider/model routing, eight transient
retries, request timeout and per-phase safety ceilings are unchanged.

## Drain before sealing a phase

The pinned native executor can resubmit a slow tail after 120 seconds and return
while the original is still running. This threshold applies to a whole example,
not an individual HTTP attempt. The registered executor delegates all submissions,
worker execution and native first-result selection to the original implementation.
It records every future, including losing duplicates, and waits at phase exit
before restoring the transport/meter or sealing the final ledger and receipt.

Late paid responses are persisted and counted. A late fatal operational failure
aborts the phase even if its winning future succeeded. After the phase deadline,
queued work is cancelled while running work unwinds under its original bounded
transport. A process supervisor enforces the outer wall ceiling and preserves
an ABORTED stage if forced termination is necessary; incomplete/unknown usage
must be audited from preserved ledgers, never replaced with zero.

This is a correction to accounting and operational validity, not a new candidate
selection or semantic retry rule. Completed scientific results require
`phase_futures.drained=true` and zero pending work.

## Process scheduling and resource admission

The scheduler accepts exactly one stage containing all five tasks and five exact,
unused, user-approved phase grants. It validates all grants before dispatch and
never promotes a template, updates a grant, chooses by observed score, retries a
failed scope, or reallocates a scientific budget.

- At most two isolated phase processes: one retrieval task and one nonretrieval
  task. DSPy/global cache/settings, metering and model transport are never shared
  by two phase executions in one interpreter.
- Fixed priority: HoVer, HotpotQA, IFBench, AIME-2025, LiveBench-Math. Within the
  retrieval lane HoVer precedes HotpotQA; available light work can fill the other
  lane. Results do not influence priority.
- LiveBench-Math runs alone to avoid extra cross-task contention on its Windows
  scorer workers and existing eight-second deadline.
- Initial reservations are 5GiB per retrieval task, 1GiB per ordinary light task,
  2GiB for LiveBench, plus 1GiB free headroom. Admission accounts for each active
  child's still-unallocated reservation using its process-tree USS. These are
  conservative planning reservations, not promises of peak memory or hard OS
  memory limits. A stage waiting without active work aborts after one hour.
- Individual phase wall limits include process startup in scheduler supervision.
  A failed, over-time or invalid-receipt child stops further dispatch and aborts
  the stage; other active phase process trees are terminated. No retry is hidden.

Windows job objects use kill-on-close semantics. A child announces its interpreter
PID and waits before any provider creation. The supervisor verifies lineage and
attaches both the venv redirector and actual interpreter before releasing it.
This also closes descendants after an early parent exit or supervisor death.
stdout/stderr, events and partial receipts remain in ignored private directories.

Account RPM/TPM limits have not been measured. The two-process envelope is not a
verified provider throughput limit. This amendment introduces no speculative
provider quota, adaptive concurrency or changed request timeout. In particular,
queueing must not be added carelessly inside a native trajectory because that
time also counts toward native slow-tail resubmission.

## Validation/Test barriers

The operational stages are:

```text
authorized Canary -> all five searches and selection freezes
                 -> all five baseline Test evaluations
                 -> all five selected-program Test evaluations
```

Every baseline/final-Test grant must bind all five successful, drained search
receipts and their actual frozen selected-program files. Final-Test grants also
bind all five successful baseline receipts. These checks apply to direct phase
commands as well as the scheduler; one task finishing early does not open Test.
Baseline and selected Test for a task do not run concurrently against one cache.

## Retrieval loading

The finished native BM25S index is loaded with `mmap=True`. Corpus rendering,
document order, tokenization, scoring, k=7/10, sorting and original search function
are unchanged. The corpus list remains process-local, so this does not make two
full retrieval tasks cheap enough to schedule together. No index is rebuilt.

## Commands and authorization boundary

Prepare an inactive stage template in a fresh ignored output path:

```powershell
python scripts/run_gepa_paper_schedule.py template --phase search --output runs/fresh_search_schedule.json
```

The template remains `approved_by=null`, `real_api_allowed=false`,
`READY_TO_RUN=false`; dirty-source templates leave `source_sha=null`. Bind the
actual committed clean source, exact v2 phase grants, hashes, scope ID and finite
wall limit before seeking/recording the corresponding user authorization.
Preparing a template grants no permission and does not consume any API scope.

After exact stage and phase authorization, the guarded entrypoint is:

```powershell
python scripts/run_gepa_paper_schedule.py execute --plan runs/authorized_stage.json
```

Use the fixed paper environment with the role environment variables supplied by
the ignored local launcher/environment. The coordinator and children both verify
the frozen source and environment. Existing source-32fc87e handoffs do not become
new authorizations through this amendment.

Offline verification:

```powershell
python scripts/verify_gepa_paper_suite_offline.py pytest -- -q tests/test_gepa_paper_concurrency.py tests/test_gepa_paper_control.py
python scripts/verify_gepa_paper_suite_offline.py integration --python runs/gepa_paper_suite_20261031/venv/Scripts/python.exe -- --concurrency-only --output runs/fresh_concurrency.json
python scripts/verify_gepa_paper_suite_offline.py integration --python runs/gepa_paper_suite_20261031/venv/Scripts/python.exe -- --lifecycle-only --output runs/fresh_lifecycle.json
```

These commands remove credentials and deny sockets in all spawned interpreters.
The process probes use an explicitly synthetic script and the lifecycle fixture
uses a synthetic authorization validator; neither establishes real API permission.
The completion report distinguishes tests, resource/query parity, reused evidence
and pending clean-source freeze from actual throughput or model availability.
