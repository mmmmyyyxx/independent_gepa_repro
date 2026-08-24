from __future__ import annotations

import json

from independent_gepa.bundle import validate_bundle, write_canonical_json
from independent_gepa.reporting import build_v17_report
from tests.helpers import make_bundle


def _accounting(tokens: int = 1000) -> dict:
    return {
        "roles": {
            "task": {
                "logical_calls": 10,
                "real_requests": 8,
                "cache_hits": 2,
                "prompt_tokens": tokens // 2,
                "completion_tokens": tokens // 4,
                "total_tokens": tokens * 3 // 4,
                "estimated_cost": 0.001,
                "cost_status": "estimated",
            },
            "reflection": {
                "logical_calls": 2,
                "real_requests": 2,
                "cache_hits": 0,
                "prompt_tokens": tokens // 8,
                "completion_tokens": tokens // 8,
                "total_tokens": tokens // 4,
                "estimated_cost": 0.001,
                "cost_status": "estimated",
            },
        },
        "real_requests": 10,
        "total_tokens": tokens,
        "estimated_cost": 0.002,
        "cost_status": "estimated",
    }


def test_deterministic_comparison_report_and_decision(tmp_path) -> None:
    bundles = {
        seed: validate_bundle(
            make_bundle(tmp_path / f"bundle-{seed}", experiment_seed=seed),
            require_formal=False,
            stage="formal",
        )
        for seed in (56, 57, 58)
    }
    run_root = tmp_path / "runs" / "formal"
    for seed, bundle in bundles.items():
        public = run_root / f"seed{seed}" / "public"
        members = []
        for member_id in range(5):
            members.append(
                {
                    "member_id": member_id,
                    "gepa_seed": seed * 1000 + member_id,
                    "best_prompt_hash": str(member_id) * 64,
                    "initial_prompt_hash": "a" * 64,
                    "candidate_count": 3,
                    "logical_evaluations": 8,
                    "initial_optimization_accuracy": 0.5,
                    "final_optimization_accuracy": 0.6,
                    "termination_reason": "logical_cap_stop",
                    "completed": True,
                    "provider_accounting": _accounting(200),
                }
            )
        write_canonical_json(
            public / "search_summary.json",
            {
                "bundle_hash": bundle.overall_hash,
                "final_team_frozen": True,
                "members": members,
                "budget": {"consumed_total": 40},
                "provider_accounting": _accounting(1000),
                "wall_clock_seconds": 1.0,
            },
        )
        common = {
            "bundle_hash": bundle.overall_hash,
            "team_vote_accuracy": 0.76,
            "oracle_coverage": 0.8,
            "member_accuracies": [0.7] * 5,
            "mean_member_accuracy": 0.7,
            "minimum_member_accuracy": 0.7,
            "invalid_rate": 0.0,
            "member_gains": [0.1] * 5,
            "N_positive": 5,
        }
        write_canonical_json(public / "development_summary.json", common)
        write_canonical_json(public / "test_summary.json", common)
        write_canonical_json(
            public / "initial_parity_summary.json",
            {"bundle_hash": bundle.overall_hash, "parity_status": "PASS"},
        )
    output = tmp_path / "reports" / "v17"
    summary = build_v17_report(
        bundles=bundles,
        run_root=run_root,
        output=output,
        repository_commit="1" * 40,
        reference_commit="2" * 40,
    )
    assert summary["decision_label"] == "CURRENT_END_TO_END_DIRECTION_LOW_PRIORITY"
    assert (output / "comparison_vs_v17.csv").is_file()
    assert (output / "budget_reconciliation.csv").is_file()
    assert json.loads((output / "research_decision.json").read_text())["beats_s4_seed_count"] == 3
    assert "Frozen-Test VoteAcc" in (output / "README.md").read_text(encoding="utf-8")
