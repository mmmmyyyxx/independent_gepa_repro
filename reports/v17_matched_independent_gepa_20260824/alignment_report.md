# Alignment report

- Reference identity: V17 formal 5-arm, 3-seed frozen artifacts.
- Model/request: qwen3-14b, thinking false, temperature 0, max tokens 1800.
- Splits: frozen 75 optimization / 50 development / 125 test.
- Initialization: five identical prompt hashes within every seed.
- Search: official GEPA v0.1.1, one mutable `system_prompt`, isolated state,
  member-only correctness feedback, deterministic seeds 56000-58004.
- Aggregation: equal plurality; tie and invalid are incorrect.
- Budget: realized V17 S4 total model tokens, equal fifths, 5% hard ceiling.
- Seed56 initial aggregate parity passed at 50/75.
- Seed57 initial aggregate parity failed at 50/75 versus frozen 51/75.

The prompt/config/request identities match. The historical per-example answer
vectors did not replay exactly at temperature zero, demonstrating that the
hosted backend is not an exact historical replay oracle. The one-point Seed57
aggregate drift triggers HOLD under the frozen parity gate.
