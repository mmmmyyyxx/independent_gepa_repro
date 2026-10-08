# Reviewed replacement attempt: authorization pending

Status: **HOLD; READY_TO_RUN=false.** No replacement API request is authorized.
The original run failed its candidate contract and consumed the one-shot grant.
Its sealed evidence and classification remain immutable.

The proposed replacement uses the same frozen MATH Optimize60, initial procedure,
Solver qwen3-8b (thinking false, temperature0.2), reflection qwen3.7-flash,
seven reset windows/targets, seeds, native GEPA and exact A4 request/scoring
contract. The changed behavior repairs source copying and visible-output
conformance checks. It adds no successful observed prompt or manual strategies.

| Limit | Reviewed proposal |
|---|---:|
| New charged-token ceiling, Solver plus reflection | 3,000,000 |
| New physical-attempt ceiling | 9,000 |
| Native metric scores per window | 36 |
| Generated proposals per window | 6 |
| Changed Full60 candidates per window | At most4 |
| Shadow / Validation / Test calls | 0 |
| Team commits / process resume | Denied |

The implementation source is `07527af8c346567107ae84a7036c633f8f995536`.
The exact source inventory, config, models, runtime, bundle, limits and reviewed
run arguments are hashed in [proposal.json](proposal.json). It is a proposal,
not an execution manifest. The complete offline suite passed98 tests with
credentials removed and sockets blocked. An additional evidence-only commit
may change HEAD without changing the reviewed source inventory. Execution still
requires a fresh exact commit/command freeze after a new explicit user grant,
and must match the reviewed source inventory and config.

The original protocol states: "An interrupted run consumes the one-shot grant
and cannot automatically restart." The original task text cannot authorize
this replacement merely because its source or attempt identity changed.

After new authorization, create a fresh frozen attempt and use the exact
reviewed command, in the pinned math environment:

```powershell
python scripts/math_a4_comparison.py run --bundle data/private_bundles/math_a4_matched_gepa_seed81_20261008_v1 --config configs/math_a4_matched_guard_repair.yaml --freeze experiments/protocols/math_a4_guard_repair_pending/frozen_attempt.json --private-output runs/math_a4_matched_gepa_seed81_guard_repair_pending --public-output reports/math_a4_matched_gepa_seed81_guard_repair_pending --allow-real-api
```

This command is not currently runnable: its authorized frozen attempt does not
exist. Neither the available ledger capacity nor the prepared proposal grants
API authorization. No hybrid or promotion experiment is included in this scope.
