# Independent-GEPA under a matched prompt-team evaluation protocol

This repository implements an external, auditable baseline for comparing five
independently optimized GEPA prompts with a five-member prompt-team method.
Each member receives the same fixed logical evaluation budget, owns an isolated
GEPA run and checkpoint, and contributes its own independently selected best
candidate directly to the final plurality-voting team.

The repository deliberately does not import or execute optimizer code from
`multi_agent_diversity`. A one-time, read-only exporter freezes comparison
inputs into a self-contained bundle; all optimization and final evaluation
consume only that validated bundle.

## Offline setup and verification

Python 3.11 is the target runtime. The official GEPA checkout is a submodule at
`vendor/gepa`, pinned to tag `v0.1.1`, commit
`b4dbb55b7601dac448cdb836d5a401ca7d9eb920`.

```powershell
git submodule update --init
python -m compileall -q src scripts tests
python -m pytest -q
python scripts/verify_environment.py
git diff --check
```

No command makes a real model request unless both the configuration and CLI
explicitly allow it. Stage one is offline-only and uses injected fake task and
reflection transports.

## Main commands

```powershell
python scripts/export_comparison_bundle.py --help
python scripts/validate_comparison_bundle.py --help
python scripts/preflight.py --help
python scripts/run_independent_gepa.py --help
python scripts/evaluate_final_team.py --help
python scripts/audit_run.py --help
```

Private bundles, prompts, examples, responses, caches, and run checkpoints are
ignored. Public reports may contain only identities, hashes, aggregate
statistics, accounting, and audit status.

## Frozen-bundle export contract

`export_comparison_bundle.py` takes a data-only JSON specification. The spec
names five ordered prompt sources (text files or slots in a JSON array), three
split sources, model/parser/budget contracts, opaque source and reference-result
identities, and the experiment seed.
Split sources may already be canonical JSONL or may explicitly declare CSV
field mappings. For the source project's BBH files, the CSV entry must declare
`question_options_format: "bbh_embedded_options"`; the exporter then separates
the `Options:` block without importing any source-project Python.

The v3 exporter normalizes LF, CRLF, and CR inside CSV fields before parsing
the BBH `Options:` block, while preserving each raw source-file SHA-256 as
provenance. Every canonical example freezes its own contiguous
`option_labels`, so three-option and four-option questions can coexist without
weakening answer-domain checks.

The source-aligned parser requires exactly one standalone `FINAL_ANSWER` line.
Duplicate lines are invalid even when they contain the same answer, and frozen
golden fixtures check parsed option, validity, correctness, and the original
`task_parser_v1` failure type.

The model contract separates the shared task-model transport, reference
Teacher/Critic/Student metadata, and the native Independent-GEPA reflection
configuration. The budget contract likewise separates an audited Pilot budget
from the not-yet-frozen Formal budget. Bundle integrity and Pilot readiness can
therefore pass while Formal readiness remains an explicit HOLD.

The output validator checks all contract and data file hashes, frozen raw-source
provenance fields, ordered example IDs and hashes, member/prompt mapping,
disjointness, exact split sizes, model and parser identities, initial-metric
availability, voting and tie rules, stage-specific budget availability, and a
canonical overall identity hash.

## Model profile for subsequent experiments

Experiments started after the 2026-09-04 correction use `qwen3-14b` for the optimized prompt's
actual task rollouts and set `enable_thinking: false`. GEPA reflection and
candidate prompt generation use `qwen3.7-flash`; the evaluator and optimizer
identities are also frozen as `qwen3.7-flash` so no control-model field can
silently retain the prior model.

Independent-GEPA correctness remains the existing deterministic strict parser
plus gold-label comparison. There is no LLM judge in that scoring path, so the
evaluator model makes zero scoring calls; any evaluator-assisted feedback path
is required by the bundle and run configuration to use `qwen3.7-flash`.

The model-profile migration derives new bundles from the prior frozen bundles.
It preserves prompt, split, parser, budget, seed, voting, and reference-result
files, and marks prior-run initial metrics as not evaluated. The authoritative
minimal real provider smoke result is published in
`reports/model_routing_smoke_20260904.json`. The 2026-09-03 qwen3-8b smoke is
retained as historical evidence but is superseded for future experiments.

## Fixed GEPA adapter

The implementation calls the actual v0.1.1 `gepa.optimize` API with one
candidate component, `system_prompt`. `trainset` and `valset` both receive the
optimization split; development and test are inaccessible during search.
`IndependentGEPAAdapter.evaluate` returns per-example `EvaluationBatch` scores
and current-member traces, and `make_reflective_dataset` emits only the current
prompt, task input, current response, strict parse result, gold, correctness,
validity, and failure reason.

GEPA's internal `total_metric_calls` omits task evaluations used inside
reflection minibatches. The comparison therefore uses an external atomic
logical-evaluation ledger and a ledger-aware stop callback. The upstream count
is not substituted for the fair-budget count.

The logical ledger is atomically persisted per member. A completed member is
restored from its identity-checked private result without re-entering GEPA.
For an interrupted member, the fixed GEPA implementation re-evaluates the seed
before loading `gepa_state.bin`; those actually performed evaluations are
counted by the external ledger, as required by the resume budget contract.

## Historical V17 matched protocol

The completed August 24 protocol targeted `qwen3-14b` with thinking disabled,
temperature zero, 1,800 output tokens, seeds 56/57/58, the frozen 75/50/125 V17 splits,
shared-identical initialization, and plurality voting with ties counted wrong.
`scripts/export_v17_comparison_bundles.py` reads the clean sibling repository
without importing it and freezes one self-contained bundle per seed.

The primary search budget is total task-plus-reflection model tokens. Each
seed's realized V17 S4 token count is divided equally among the five independent
members; a calibrated pre-iteration reserve and a 5% hard ceiling prevent an
accepted overrun. Task and reflection accounting is persisted independently
for every member.

The August 24 three-seed formal run is complete. Its approved initial parity
policy freezes prompt/model/request/data identities and requires all five
shared-initialized members to agree within the canonical current evaluation;
historical hosted-model output differences remain diagnostics and are never
resampled or cherry-picked. Results are published in
`reports/v17_matched_independent_gepa_20260824`.
