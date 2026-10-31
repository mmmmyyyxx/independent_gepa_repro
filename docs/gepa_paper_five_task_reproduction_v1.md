# Five-task GEPA author-artifact reproduction preparation

This is a separate protocol requested on 2026-10-31. It supersedes the matched-team
defaults **only inside this new experiment**. Existing experiments, the read-only
`vendor/gepa` checkout, deployment routes, MATH scorer, results and authorizations
are unchanged. The sibling repository is not a runtime dependency.

The user selected GEPA's native Pareto main row without Merge, author-script seeds
and repetition count, author reflection defaults, and a verified Windows adaptation.
The user explicitly chose to retain/disclose HoVer's one identical Train/Validation
claim, and to defer full BM25 index construction until memory is available.
These choices authorize preparation, not paid inference.

## Authority and scope

Use [the paper, v2, Appendix E](https://arxiv.org/html/2507.19457v2#A5),
[the author reproduction artifact](https://github.com/gepa-ai/gepa-artifact/tree/cbefbc1aa0f43dd39874ec4bf42211365dbda42e)
and its [modified DSPy fork](https://github.com/gepa-ai/dspy/tree/62dc3b634d7dc0c4889abcf905cb4c391ea6b396).
Actual code controls the concrete protocol. The pinned identities are:

- Artifact: `cbefbc1aa0f43dd39874ec4bf42211365dbda42e`.
- DSPy `gepa_study`: `62dc3b634d7dc0c4889abcf905cb4c391ea6b396`.
- Engine: `gepa_artifact.gepa.gepa.GEPA`, with original module programs/feedback.
- The repository's existing official GEPA v0.1.1 remains untouched; substituting
  that newer engine would require a separately identified method reproduction.

This reproduces the author algorithm/benchmark setup with the requested OpenLux
deployment. It cannot certify identical model weights, provider routing, historical
dependency versions, random samples from the provider or identical paper scores.
The author artifact has no complete historical dependency lock. The new Windows
lock is a tested reconstruction, not a recovered historical lock.

## Frozen preparation parameters

| Task | Train | Native selection Validation | Test rows | Native search threshold | Original metric |
|---|---:|---:|---:|---:|---|
| HotpotQA | 150 | 300 | 300 | 6,871 | DSPy normalized answer exact match |
| IFBench | 150 | 300 | 294 | 3,593 | Loose fraction of constraints satisfied |
| HoVer | 150 | 300 | 300 | 7,051 | All gold document titles retrieved |
| AIME-2025 | 45 | 45 | 150 | 1,839 | Integer equality on DSPy answer field |
| LiveBench-Math | 121 | 121 | 126 | 1,839 | Author task-specific scoring dispatch |

The five search thresholds sum to **21,193**. This is not a token ceiling, physical
request ceiling or guaranteed exact spend. Baseline and final Test are separate;
one baseline plus one selected-program evaluation amounts to 2,340 logical Test
rows in total. Reflection and individual module requests are recorded separately.
Only token accounting is requested; there is no assumed monetary price table.

Author launch seeds are `[0]`, giving one run per task, not three seed42 repeats.
Each task starts from its own original DSPy program. HotpotQA and HoVer each have
four optimizable predictors; IFBench has two; each math program has one CoT predictor.
There is no five-member voting team or Role/Strategy/Answer conversion in this protocol.

Preserve `run_linearized_gepa=False`, `use_merge=False`,
`set_for_merge_minibatch='val'`, `track_scores_on='val'`, minibatch size3,
`skip_perfect_score=True` and the original final maximum aggregate Validation rule.
Do not add CurrentBest selection, candidate content guards, length/no-op filters,
an outer20-round cap, a3000-evaluation cap or a new scorer fallback.

The author code leaves `teacher_lm=None`; reflection uses the configured task LM.
Both roles therefore use OpenLux, requested model
`openai/gpt-4.1-mini-2025-04-14`, temperature1.0 and `max_tokens=16384`.
The unprefixed wire ID is the dated GPT-4.1 Mini ID. Availability of that exact
deployment remains unverified without a separately authorized canary. Never
silently substitute an undated alias, another provider or another model.
The source sets a completion-token limit; do not invent a16K combined-context
truncation policy from the paper's prose. Record actual request parameters.

The published launcher requests32 final-evaluation threads. Native GEPA receives
`num_threads=None` in that script and resolves it through `os.cpu_count()`.
Record the actual effective value in any future exact runtime freeze; do not claim
the author script consistently propagates the requested thread count.

## Data identities and disclosed limitations

Membership is reconstructed using the exact author class bodies and inherited
`Benchmark` splitting/trimming (including seed1 sampling), then hashed in order.
Hotpot's large Parquet source is hydrated by selected row positions, without
expanding all90k contexts; the positions and resulting payloads are preserved.
The complete original IFBench loader is independently checked against preparation.
LiveBench metadata datetimes use a reversible tagged ISO representation.

LiveBench uses revision `bb66571c8ccf32d3df9e6f48b920d3770ff4aacb`:368 rows,
whose latest repository commit predates the paper's July30,2025 snapshot. Preserve
the author's `int(n*0.33)`/`int(n*0.66)` slicing, yielding121/121/126, rather than
inventing exactly equal integer thirds. The full source and ordered memberships
are pinned in the preparation inventory.

HoVer uses the original training release filtered to exactly three unique support
documents, shuffles at seed0, then inherits the author's split/trimming. There is
one identical claim across Train and Validation. The user explicitly accepted
retention and disclosure. Test has no content overlap with either search split.
Do not silently deduplicate or call all splits strictly content-disjoint.

AIME Test comprises30 unique2025 problems repeated five times. The original
request cache is retained; repeated rows need not yield independent provider
realizations. Report150 logical rows,30 unique problems and actual cache/request
counts separately. The older2022–2024 pool contains90 problems, split45/45.

The author cache warm-starts GEPA from a MIPRO cache in the full comparison script.
No such paid reference cache is imported here and no extra MIPRO experiment is
authorized. A future GEPA-only launch must explicitly identify its fresh cache
namespace and this operational departure, rather than wait forever for an absent
MIPRO run or claim identical historical cache realizations.

Train feeds reflection/minibatch evaluation. Validation feeds native Pareto and
final candidate selection. Test outcomes must never feed search, method choices,
memory or candidate selection. Dataset preparation reads memberships and schemas,
not model Test outcomes; this task performs no benchmark inference.

## Windows and resource adaptation

The original LiveBench AMPS helper launches a nested multiprocessing function,
which cannot be pickled by Windows spawn. `paper_suite.windows` replaces only its
process transport. The child loads the same pinned scoring source and calls the
same `is_equiv`; extraction, normalization, symbolic comparison, numeric tolerance,
exceptions, score and feedback remain authored functions. Bind the helper to the
actual author metric module with `install(artifact, author_module=amp_module)`.
The integration check exercises that actual metric graph as well as the isolated oracle.

The original eight-second wall deadline remains. Spawn startup contributes to
that deadline on Windows. Direct original-function vs spawn parity demonstrates
result/feedback agreement on the finite checked inputs, not identical Linux timing
or exhaustive equivalence over every possible expression. Timeout/crash tests
also verify cleanup, a subsequent request, and large-result IPC without deadlock.
An unexpectedly dead worker without a result is an operational halt, not a
fabricated wrong answer. Ordinary mathematical exceptions and deadline results
retain the author's handling. This distinction is part of the Windows amendment.

NLP download calls are suppressed during offline checks only after local spaCy and
NLTK resources are verified. Constraint checkers are unchanged. Model inference is
socket-blocked and credentials are removed from verification processes and children.

Wikipedia2017 is downloaded and its corpus unpacked outside upstream. The user
deferred the full BM25 index due to actual available memory. Build later with the
preserved author transformation, English stemmer/stopwords and BM25(k1=0.9,b=0.4):

```powershell
runs/gepa_paper_suite_20261031/venv/Scripts/python.exe scripts/prepare_gepa_paper_retriever.py --index
```

The default preparation guard requires8GiB currently available memory before
starting a full index build. That is an engineering guard, not an experiment
token/rollout budget. The command preserves any existing index and publishes only
hashes/counters. A future run must verify the finished index receipt and bind that
local resource; an unprepared run must not download/rebuild resources mid-search.

## Original operational limitations and launch gates

`max_metric_calls` is an original before-iteration threshold. A whole iteration
can cross it. More subtly, all-perfect minibatch and failed-proposal skip paths do
not advance the native counter. Preserve this fact in a faithful-source run and
meter actual logical evaluations, physical attempts and tokens independently.
Never present the thresholds as strict equal physical compute. Do not silently
repair that counter inside the author algorithm and retain the same method name.

The author runner uses `num_retries=0` and broad exception handling. The new
`paper_author_engine_metered_transport_v1` is an explicitly identified operational
amendment: it wraps the physical completion call underneath the original DSPy
cache, permits up to8 retries of transient network/408/429/5xx failures, and uses
a120-second request timeout with bounded backoff. Credentials, model-not-found,
schema and persistence errors halt. There are no additional semantic retries.
Paid response bodies are persisted privately before scoring. Failed-attempt token
usage is explicitly unknown; do not invent zero usage for those attempts.

Root-program instrumentation reserves one logical attempt before execution,
including cached observations, and preserves predictor names, outputs and native
selection/stopping. Nested calls are not new examples. Native and independent
counters remain separate. Finite logical/physical/wall operational limits must be
provided in the exact grant; hitting one marks the attempt ABORTED, never COMPLETE.
The request timeout and retry backoff are bounded by remaining wall allowance;
in-flight local work is checked at execution boundaries. None of these controls
silently redefines the original search budget or final candidate rule.

The guarded entrypoint is `scripts/run_gepa_paper_suite.py`. It accepts only the
new protocol's exact, single-use, source/config/data/environment/deployment-bound
grant. Canary, baseline, search and final Test are separate phases with explicit
model roles. Test loads require the frozen selected program and successful search
receipt. Source/data/provider identities are checked again before completion.
There is no historical checkpoint continuation or automatic rerun. A task-scoped
cache can share identical requests across authorized phases of the same frozen
task; another deployment, source, task or repeat cannot reuse it.

Preparation creates no positive API grant. `READY_TO_RUN=false` until the deferred
index, exact provider/model canary, clean committed source/runtime freeze and new
single-use authorization are complete. The non-authorizing template is reviewable
in the protocol directory. This task does not authorize running the raw research
script or this guarded entrypoint. No commit or push is performed by preparation.
Original and historical results remain untouched.

## Reproducible offline commands

```powershell
python scripts/fetch_gepa_paper_sources.py --direct
python scripts/setup_gepa_paper_environment.py --direct
runs/gepa_paper_suite_20261031/venv/Scripts/python.exe scripts/prepare_gepa_paper_nlp.py --direct
python scripts/prepare_gepa_paper_suite.py source-audit --output runs/source_audit_fresh.json
python scripts/verify_gepa_paper_suite_offline.py data --python runs/gepa_paper_suite_20261031/venv/Scripts/python.exe --output runs/paper_data_fresh
python scripts/verify_gepa_paper_suite_offline.py integration --python runs/gepa_paper_suite_20261031/venv/Scripts/python.exe --output runs/integration_fresh.json
python scripts/verify_gepa_paper_suite_offline.py pytest -q
python scripts/verify_gepa_paper_suite_offline.py compile
```

Use fresh output paths for immutable receipts. Public source/data downloads are
distinct from the offline, socket-blocked verification campaign and do not invoke
model APIs. Private inputs, prompts, questions, labels, model outputs, caches and
machine paths remain ignored; publish only sanitized inventories and metrics.
