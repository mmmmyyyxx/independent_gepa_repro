# OpenLux model-name amendment preparation

The user requested replacing the paper-suite Solver request name with C-EVOLVE's
`gpt-4.1-mini` and retrying one lightweight Canary. The new protocol is
`gepa_paper_five_tasks_openlux_qwen37_alias_windows_v3`.
Parent source: `f94ffa2e87e8c92fb1536c63bd087017e9bcf1cb`.

Only the Solver model name changes scientifically. The native GEPA/Pareto search,
Qwen optimizer, temperature1/output16384, author seed0/repeats, frozen data,
scorers, budgets, concurrency and retry policy are unchanged. V2 configuration,
manifest, failed Canary, raw responses and consumed authorizations are preserved.
A successful alias request would not prove a fixed backend snapshot.

Offline verification:418 current tests passed,18 cases deselected,4 historical
scoring modules excluded;3 warnings. Production compileall and the four-phase
fake-model lifecycle pass under socket denial. Preflight rechecked2,852 data
rows,146 dependencies,159 NLP files and complete index/corpus hashes. After the
full suite, one trailing blank line was removed from a test file; that file's
tests were rerun and the final inventory regenerated. Runtime source bytes
remain those exercised by the full suite. Existing scoring/index result parity
is reused because its source/inputs are unchanged. No API calls occurred during
these checks; no actual throughput was measured.

The [amendment](../../docs/gepa_paper_openlux_alias_v3.md),
[manifest](../../experiments/protocols/gepa_paper_five_tasks_openlux_qwen37_alias_windows_v3/manifest.json),
[checks](checks.json) and [final source inventory](source_inventory.json) bind the
reviewed configuration. Public readiness remains false:formal search/Test are
not authorized. Only the freshly frozen lightweight Canary is authorized by
the user's request. Its runtime/error/timing evidence stays in ignored runs;
this preparation snapshot is not a claim that a real model call succeeded.
