# OpenLux Solver alias amendment V3

The user requested on 2026-10-31 that the paper GEPA Solver use the same
OpenLux request model name as the successful C-EVOLVE configuration:
`gpt-4.1-mini`. DSPy uses `openai/gpt-4.1-mini`; LiteLLM removes the provider
prefix on the HTTP wire. The dated request name failed one earlier Canary;
its missing HTTP error detail prevents attributing that failure conclusively.

This supersedes V2 only for new attempts. It preserves Qwen3.7-Flash reflection,
temperature1, output16384, author seed0, one repetition per task, native Pareto
without Merge, all data IDs/order, scoring, budgets and the
[concurrency policy](gepa_paper_concurrency_v1.md). C-EVOLVE's output4096,
API seed42, top_p and optimizer parameter spelling are not imported.
A provider alias is not proof of a pinned backend snapshot or OpenAI equivalence.

The [V3 manifest](../experiments/protocols/gepa_paper_five_tasks_openlux_qwen37_alias_windows_v3/manifest.json)
binds the unchanged inventories and the changed configuration. Historical V2
files, responses, receipts and consumed scopes remain untouched. Runtime accepts
only V3; it has no model fallback. New clean-source authorization must bind the
new source/configuration and a fresh scope/cache. The user authorized one
lightweight Canary after the name change, not formal search or Test.

The Canary performs the existing trivial Solver and reflection requests, with
one logical-evaluation safety allowance,18 physical attempts maximum and3000s
wall ceiling. It reads no dataset examples and never selects a candidate.
Private exception-chain observation may record HTTP status and redacted errors;
it must not modify request arguments, scoring, retries or the frozen runtime.
