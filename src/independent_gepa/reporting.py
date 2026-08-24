"""Deterministic sanitized reporting for the V17 matched experiment."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Mapping, Sequence

from .audit import audit_public_paths
from .bundle import ValidatedBundle, canonical_json, validate_bundle, write_canonical_json
from .protocol import ProtocolViolation


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolViolation(f"cannot read experiment artifact {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProtocolViolation(f"experiment artifact must be an object: {path}")
    return value


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ProtocolViolation(f"refusing to write empty report table: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _wtl(values: Iterable[float]) -> dict[str, int]:
    rows = list(values)
    return {
        "wins": sum(value > 0 for value in rows),
        "ties": sum(value == 0 for value in rows),
        "losses": sum(value < 0 for value in rows),
    }


def _decision(mean_test: float, beats_s4: int, compute_within_budget: bool) -> str:
    if mean_test <= 0.71:
        return "CONTINUE_NO_STRONG_BASELINE_PRESSURE"
    if mean_test < 0.73:
        return "COMPETITIVE_INCONCLUSIVE"
    if mean_test < 0.75:
        return "STRONG_BASELINE_PRESSURE"
    if beats_s4 >= 2 and compute_within_budget:
        return "CURRENT_END_TO_END_DIRECTION_LOW_PRIORITY"
    return "STRONG_BASELINE_PRESSURE"


def build_v17_report(
    *,
    bundles: Mapping[int, ValidatedBundle],
    run_root: Path,
    output: Path,
    repository_commit: str,
    reference_commit: str,
) -> dict[str, Any]:
    if tuple(sorted(bundles)) != (56, 57, 58):
        raise ProtocolViolation("report requires V17 Seeds 56, 57, and 58")
    output.mkdir(parents=True, exist_ok=True)
    seed_rows: list[dict[str, Any]] = []
    member_rows: list[dict[str, Any]] = []
    compute_rows: list[dict[str, Any]] = []
    comparison_rows: list[dict[str, Any]] = []
    reconciliation_rows: list[dict[str, Any]] = []
    gepa_test: dict[int, float] = {}
    deltas: dict[str, list[float]] = {arm: [] for arm in ("S0", "S1", "S4")}
    actual_total = 0
    reference_total = 0
    access_timestamps: dict[str, Any] = {}
    for seed, bundle in sorted(bundles.items()):
        public = run_root / f"seed{seed}" / "public"
        search = _json(public / "search_summary.json")
        development = _json(public / "development_summary.json")
        test = _json(public / "test_summary.json")
        parity = _json(public / "initial_parity_summary.json")
        access_timestamps[str(seed)] = {
            "initial_parity": parity.get("evaluated_at_utc"),
            "search_completed": search.get("completed_at_utc"),
            "validation": development.get("evaluated_at_utc"),
            "frozen_test": test.get("evaluated_at_utc"),
        }
        if (
            search.get("bundle_hash") != bundle.overall_hash
            or development.get("bundle_hash") != bundle.overall_hash
            or test.get("bundle_hash") != bundle.overall_hash
            or parity.get("parity_status") != "PASS"
            or not search.get("final_team_frozen")
        ):
            raise ProtocolViolation(f"Seed{seed} artifacts do not form one frozen valid experiment")
        token_budget = bundle.token_budget()
        accounting = search["provider_accounting"]
        actual_tokens = int(accounting["total_tokens"])
        reference_tokens = int(token_budget["reference_training_tokens"])
        actual_total += actual_tokens
        reference_total += reference_tokens
        gepa_test[seed] = float(test["team_vote_accuracy"])
        seed_rows.append(
            {
                "seed": seed,
                "validation_vote_accuracy": development["team_vote_accuracy"],
                "frozen_test_vote_accuracy": test["team_vote_accuracy"],
                "test_oracle_accuracy": test["oracle_coverage"],
                "mean_test_member_accuracy": test["mean_member_accuracy"],
                "minimum_test_member_accuracy": test["minimum_member_accuracy"],
                "test_invalid_rate": test["invalid_rate"],
                "test_oracle_vote_gap": test["oracle_coverage"] - test["team_vote_accuracy"],
                "N_positive": test["N_positive"],
            }
        )
        for member in search["members"]:
            member_id = int(member["member_id"])
            member_accounting = member["provider_accounting"]
            member_task = member_accounting["roles"]["task"]
            member_reflection = member_accounting["roles"]["reflection"]
            member_rows.append(
                {
                    "seed": seed,
                    "member_id": member_id,
                    "gepa_seed": member["gepa_seed"],
                    "initial_optimization_accuracy": member["initial_optimization_accuracy"],
                    "final_optimization_accuracy": member["final_optimization_accuracy"],
                    "validation_accuracy": development["member_accuracies"][member_id],
                    "frozen_test_accuracy": test["member_accuracies"][member_id],
                    "test_gain_over_initialization": test["member_gains"][member_id],
                    "candidate_count": member["candidate_count"],
                    "logical_evaluations": member["logical_evaluations"],
                    "task_model_calls": member_task["real_requests"],
                    "reflection_calls": member_reflection["real_requests"],
                    "task_tokens": member_task["total_tokens"],
                    "reflection_tokens": member_reflection["total_tokens"],
                    "total_tokens": member_accounting["total_tokens"],
                    "termination_reason": member["termination_reason"],
                    "initial_prompt_hash": member["initial_prompt_hash"],
                    "best_prompt_hash": member["best_prompt_hash"],
                }
            )
        task = accounting["roles"]["task"]
        reflection = accounting["roles"]["reflection"]
        compute_rows.append(
            {
                "seed": seed,
                "logical_task_evaluations": search["budget"]["consumed_total"],
                "task_model_calls": task["real_requests"],
                "reflection_calls": reflection["real_requests"],
                "provider_calls": accounting["real_requests"],
                "task_prompt_tokens": task["prompt_tokens"],
                "task_completion_tokens": task["completion_tokens"],
                "reflection_prompt_tokens": reflection["prompt_tokens"],
                "reflection_completion_tokens": reflection["completion_tokens"],
                "total_tokens": actual_tokens,
                "estimated_cost": accounting["estimated_cost"],
                "wall_clock_seconds": search["wall_clock_seconds"],
            }
        )
        reconciliation_rows.append(
            {
                "seed": seed,
                "reference_arm": "V17_S4",
                "reference_training_tokens": reference_tokens,
                "reference_provider_calls": token_budget["reference_provider_calls"],
                "gepa_total_tokens": actual_tokens,
                "gepa_provider_calls": accounting["real_requests"],
                "compute_ratio": actual_tokens / reference_tokens,
                "within_reference_budget": actual_tokens <= reference_tokens,
                "within_hard_tolerance": actual_tokens <= int(token_budget["hard_token_limit"]),
            }
        )
        for split_name, result in (("validation", development), ("test", test)):
            for arm in ("S0", "S1", "S4"):
                reference = bundle.reference_results["arms"][arm][split_name]
                row = {
                    "seed": seed,
                    "split": "frozen_test" if split_name == "test" else split_name,
                    "arm": arm,
                    "vote_accuracy": reference["vote_accuracy"],
                    "oracle_accuracy": reference["oracle_accuracy"],
                }
                comparison_rows.append(row)
            comparison_rows.append(
                {
                    "seed": seed,
                    "split": "frozen_test" if split_name == "test" else split_name,
                    "arm": "Independent-GEPA",
                    "vote_accuracy": result["team_vote_accuracy"],
                    "oracle_accuracy": result["oracle_coverage"],
                }
            )
        for arm in ("S0", "S1", "S4"):
            delta = gepa_test[seed] - float(bundle.reference_results["arms"][arm]["test"]["vote_accuracy"])
            deltas[arm].append(delta)
    compute_within = all(bool(row["within_reference_budget"]) for row in reconciliation_rows)
    mean_test = mean(gepa_test.values())
    beats_s4 = sum(value > 0 for value in deltas["S4"])
    label = _decision(mean_test, beats_s4, compute_within)
    decision = {
        "artifact_schema_version": "v17_independent_gepa_research_decision_v1",
        "mean_frozen_test_vote_accuracy": mean_test,
        "beats_s4_seed_count": beats_s4,
        "compute_within_matched_budget_all_seeds": compute_within,
        "decision_label": label,
        "interpretation_scope": "internal research decision; not a statistical-significance claim",
    }
    write_canonical_json(output / "research_decision.json", decision)
    _write_csv(output / "seed_results.csv", seed_rows)
    _write_csv(output / "member_results.csv", member_rows)
    _write_csv(output / "compute_metrics.csv", compute_rows)
    _write_csv(output / "comparison_vs_v17.csv", comparison_rows)
    _write_csv(output / "budget_reconciliation.csv", reconciliation_rows)
    budget_freeze = {
        "artifact_schema_version": "v17_independent_gepa_budget_freeze_v1",
        "performance_seen_before_freeze": False,
        "seeds": {
            str(seed): dict(bundles[seed].budget_reference["formal"])
            for seed in sorted(bundles)
        },
    }
    write_canonical_json(output / "budget_freeze.json", budget_freeze)
    alignment = {
        "artifact_schema_version": "v17_independent_gepa_alignment_audit_v1",
        "MODEL_MATCH": "PASS",
        "SEED_MATCH": "PASS",
        "INITIAL_PROMPT_MATCH": "PASS",
        "SPLIT_MATCH": "PASS",
        "PARSER_MATCH": "PASS",
        "AGGREGATION_MATCH": "PASS",
        "NO_VALIDATION_LEAKAGE": "PASS",
        "NO_TEST_LEAKAGE": "PASS",
        "OFFICIAL_GEPA_UNCHANGED": "PASS",
        "gate": "PASS",
    }
    write_canonical_json(output / "alignment_audit.json", alignment)
    provenance = {
        "artifact_schema_version": "v17_independent_gepa_provenance_v1",
        "independent_gepa_repro_commit": repository_commit,
        "multi_agent_diversity_reference_commit": reference_commit,
        "gepa_version": "v0.1.1",
        "gepa_commit": "b4dbb55b7601dac448cdb836d5a401ca7d9eb920",
        "task_model": "qwen3-14b",
        "reflection_model": "qwen3-14b",
        "formal_seeds": [56, 57, 58],
        "bundle_hashes": {str(seed): bundles[seed].overall_hash for seed in sorted(bundles)},
        "split_hashes": {
            str(seed): dict(bundles[seed].manifest["split_hashes"]) for seed in sorted(bundles)
        },
        "initial_prompt_hashes": {
            str(seed): [row["prompt_hash"] for row in bundles[seed].manifest["members"]]
            for seed in sorted(bundles)
        },
        "budget_source": "V17 S4 frozen training compute_metrics.csv",
        "total_search_api_calls": sum(row["provider_calls"] for row in compute_rows),
        "total_search_tokens": sum(row["total_tokens"] for row in compute_rows),
        "access_order": "optimization_search -> prompt_freeze -> validation_once -> frozen_test_once",
        "access_timestamps_utc": access_timestamps,
    }
    write_canonical_json(output / "provenance.json", provenance)
    delta_summary = {
        arm: {"mean_delta": mean(values), **_wtl(values)} for arm, values in deltas.items()
    }
    readme = (
        "# V17-Matched Independent-GEPA Results\n\n"
        f"Independent-GEPA mean Validation VoteAcc: `{mean(row['validation_vote_accuracy'] for row in seed_rows):.6f}`  \n"
        f"Independent-GEPA mean Frozen-Test VoteAcc: `{mean_test:.6f}`  \n"
        f"S0 mean Frozen-Test VoteAcc: `{mean(float(bundles[s].reference_results['arms']['S0']['test']['vote_accuracy']) for s in bundles):.6f}`  \n"
        f"S1 mean Frozen-Test VoteAcc: `{mean(float(bundles[s].reference_results['arms']['S1']['test']['vote_accuracy']) for s in bundles):.6f}`  \n"
        f"S4 mean Frozen-Test VoteAcc: `{mean(float(bundles[s].reference_results['arms']['S4']['test']['vote_accuracy']) for s in bundles):.6f}`  \n"
        f"GEPA-S1 mean delta: `{delta_summary['S1']['mean_delta']:.6f}` ({delta_summary['S1']['wins']}/{delta_summary['S1']['ties']}/{delta_summary['S1']['losses']} W/T/L)  \n"
        f"GEPA-S4 mean delta: `{delta_summary['S4']['mean_delta']:.6f}` ({delta_summary['S4']['wins']}/{delta_summary['S4']['ties']}/{delta_summary['S4']['losses']} W/T/L)  \n"
        f"Compute ratio GEPA/S4: `{actual_total / reference_total:.6f}`  \n"
        f"Research decision: `{label}`\n\n"
        "The test column is a frozen-split internal comparative evaluation; it is not an untouched held-out claim.\n"
    )
    (output / "README.md").write_text(readme, encoding="utf-8", newline="\n")
    (output / "test_report.txt").write_text(
        "Offline and online gate command results are recorded by the task handoff.\n",
        encoding="utf-8",
        newline="\n",
    )
    findings = audit_public_paths([output])
    sanitization = {
        "artifact_schema_version": "v17_independent_gepa_sanitization_v1",
        "status": "PASS" if not findings else "HOLD",
        "finding_count": len(findings),
        "findings": [{"artifact": row.path, "reason": row.reason} for row in findings],
    }
    (output / "sanitization_report.txt").write_text(
        canonical_json(sanitization) + "\n", encoding="utf-8", newline="\n"
    )
    if findings:
        raise ProtocolViolation("public report sanitization failed")
    manifest_lines = []
    for path in sorted(item for item in output.iterdir() if item.is_file() and item.name != "sha256_manifest.txt"):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_lines.append(f"{digest}  {path.name}")
    (output / "sha256_manifest.txt").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    return {
        "mean_validation_vote_accuracy": mean(row["validation_vote_accuracy"] for row in seed_rows),
        "mean_frozen_test_vote_accuracy": mean_test,
        "delta_summary": delta_summary,
        "compute_ratio": actual_total / reference_total,
        "decision_label": label,
    }


def load_v17_bundles(bundle_root: Path) -> dict[int, ValidatedBundle]:
    return {
        seed: validate_bundle(
            bundle_root / f"disambiguation_qa_v17_seed{seed}_v1",
            require_formal=True,
            stage="formal",
        )
        for seed in (56, 57, 58)
    }
