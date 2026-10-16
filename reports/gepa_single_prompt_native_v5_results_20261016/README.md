# Native GEPA single-prompt comparison, 2026-10-16

Execution is complete. The final integrity audit passed for all six Test profiles: 6,247 resolved observations, zero pending requests, zero model calls by the audit.

| Arm | Repeat 1 Test300 | Repeat 2 Test300 | Repeat 3 Test300 | Mean accuracy |
|---|---:|---:|---:|---:|
| Strict Validation (`current_best`) | 219 | 220 | 225 | 73.78% |
| Native Pareto | 229 | 220 | 222 | 74.56% |

Paired differences: +10, 0, -3 correct answers. Pareto has one win, one tie and one loss; its mean advantage is 0.78 percentage points. Three repeats do not establish a stable advantage.

Both arms used seed 42, unchanged Optimize150 / Validation100 / Test300 memberships and 20 native opportunities per repeat. Generated candidates: strict 9/11/11; Pareto 13/7/14. Candidate full-Validation evaluations excluding initialization: strict 4/2/5; Pareto 6/3/5. Equal opportunity caps do not imply equal compute or the original paper's budget.

The V5 scoring amendment repaired deterministic symbolic expansion blowup. All 5,346 existing scores replayed unchanged; one already-paid unresolved score completed. Search was not rerun. Selected Prompts and memberships remained frozen; no new Reflection calls occurred. The continuation took 977.48 seconds, adding 1,072 physical attempts and 1,714,846 charged tokens. Parent plus continuation: 7,138 physical attempts and 9,199,831 charged tokens. Charged tokens include conservative failed-request accounting and are not an invoice. Network retries recovered; no pending requests remain.

The repair was motivated by exposed Test computation, so this is not a fresh confirmatory Test result. Candidate checks were native-only, with no independent anti-copy or semantic legitimacy Guard. These single-Prompt results establish neither a team-vote benefit nor superiority over A4.

Source: `2af3a379b13bbe774ffc4ccd6cc8ce314ab6fcba`; parent: `2e2b0ea285fa8ad460e61ca9a088df90b1048264`. The unchanged source passed 296 offline tests before execution. This report adds no runtime changes or API calls.

Evidence: [summary.json](summary.json), [integrity_audit.json](integrity_audit.json), [repair review](../gepa_single_prompt_scoring_repair_v5_20261016/README.md).
