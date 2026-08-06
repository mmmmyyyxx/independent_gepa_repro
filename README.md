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
names five prompt files, three split sources, model/parser/budget contract JSON
files, opaque source and reference-result identities, and the experiment seed.
Split sources may already be canonical JSONL or may explicitly declare CSV
field mappings. For the source project's BBH files, the CSV entry must declare
`question_options_format: "bbh_embedded_options"`; the exporter then separates
the `Options:` block without importing any source-project Python.

The output validator checks all contract and data file hashes, ordered example
IDs and their hashes, member/prompt mapping, disjointness, exact formal split
sizes, model and parser identities, voting and tie rules, budget allocation,
and a canonical overall identity hash.

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
