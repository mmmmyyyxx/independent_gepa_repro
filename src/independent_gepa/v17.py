"""Read-only V17 comparison-contract extraction.

This module reads frozen data and aggregate artifacts from the sibling repository. It
does not import or execute any source-project Python.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Mapping

from .bundle import canonical_json_bytes, sha256_bytes, sha256_file
from .protocol import ProtocolViolation
from .versions import TASK_REQUEST_TEMPLATE_VERSION

V17_ID = "v17_formal_5arm_3seed_20260813"
V17_SEEDS = (56, 57, 58)
ARM_SETTINGS = {
    "S0": "shared_static_reference",
    "S1": "experimental_v17_formal_generic_2x2_matched",
    "S4": "experimental_v16_efficacy_r_m2f",
}


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolViolation(f"cannot read V17 JSON artifact {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProtocolViolation(f"V17 artifact must be an object: {path}")
    return value


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return result.stdout.strip()


def verify_reference_repository(root: Path) -> dict[str, str]:
    root = root.resolve()
    head = _git(root, "rev-parse", "HEAD")
    origin_main = _git(root, "rev-parse", "origin/main")
    status = _git(root, "status", "--short")
    if head != origin_main or status:
        raise ProtocolViolation("reference repository must be clean with HEAD == origin/main")
    return {"reference_repository_head": head, "reference_origin_main": origin_main}


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _initial_vector(reference_root: Path, seed: int) -> tuple[list[str | None], str]:
    source = reference_root / "strict_splits_bbh_seed42" / "disambiguation_qa" / "opt.csv"
    rows = _csv_rows(source)
    cache = (
        reference_root
        / "runs"
        / V17_ID
        / f"seed{seed}"
        / "disambiguation_qa"
        / f"shared_static_reference_seed{seed}"
        / "_solver_cache.sqlite"
    )
    if not cache.is_file():
        raise ProtocolViolation(f"missing V17 initial solver cache for Seed{seed}")
    with sqlite3.connect(f"file:{cache.as_posix()}?mode=ro", uri=True) as connection:
        answers = {
            str(question_hash): json.loads(str(answer_json))
            for question_hash, answer_json in connection.execute(
                "SELECT question_hash, answer_json FROM solver_cache WHERE state = 'ready'"
            )
        }
    vector: list[str | None] = []
    for row in rows:
        question_hash = hashlib.sha256(str(row["question"]).encode("utf-8")).hexdigest()
        answer = answers.get(question_hash)
        if answer is None:
            raise ProtocolViolation(f"V17 initial cache lacks optimization question {question_hash}")
        parsed = str(answer.get("answer", "")).strip().upper() if answer.get("valid") else None
        vector.append(parsed or None)
    return vector, sha256_bytes(canonical_json_bytes(vector))


def _parser_contract(reference_root: Path) -> dict[str, Any]:
    source_parser = reference_root / "multi_dataset_diverse_rl" / "tasks.py"
    source_contract = (
        reference_root / "multi_dataset_diverse_rl" / "evaluation" / "output_contract.py"
    )
    fixtures = [
        ("valid_with_reasoning", "Reason carefully.\nFINAL_ANSWER: A", "stop", "A", ["A", "B", "C"], "A", True, True, "valid"),
        ("case_space_parentheses", " final_answer : (b) ", "stop", "A", ["A", "B", "C"], "B", True, False, "valid"),
        ("missing_line", "Reasoning without a marker", "stop", "A", ["A", "B", "C"], None, False, False, "missing_final_answer"),
        ("marker_inside_prose", "Mention FINAL_ANSWER: A inside prose", "stop", "A", ["A", "B", "C"], None, False, False, "missing_final_answer"),
        ("duplicate_same", "FINAL_ANSWER: A\nFINAL_ANSWER: A", "stop", "A", ["A", "B", "C"], None, False, False, "multiple_final_answers"),
        ("duplicate_different", "FINAL_ANSWER: A\nFINAL_ANSWER: B", "stop", "A", ["A", "B", "C"], None, False, False, "multiple_final_answers"),
        ("empty_payload", "FINAL_ANSWER:", "stop", "A", ["A", "B", "C"], None, False, False, "unparseable_final_answer"),
        ("illegal_letter", "FINAL_ANSWER: Z", "stop", "A", ["A", "B", "C"], None, False, False, "out_of_domain_answer"),
        ("trailing_explanation", "FINAL_ANSWER: A because it is best", "stop", "A", ["A", "B", "C"], None, False, False, "out_of_domain_answer"),
        ("four_option_valid", "FINAL_ANSWER: D", "stop", "A", ["A", "B", "C", "D"], "D", True, False, "valid"),
        ("finish_reason_does_not_override_text_parser", "FINAL_ANSWER: A", "length", "A", ["A", "B", "C"], "A", True, True, "valid"),
    ]
    return {
        "schema_version": "parser_contract_v2",
        "source_parser_version": "task_parser_v1",
        "source_parser_sha256": sha256_file(source_parser),
        "source_output_contract_version": "task_output_contract_v1",
        "source_output_contract_sha256": sha256_file(source_contract),
        "answer_format": "option_letter",
        "final_answer_line": {
            "regex": r"^\s*FINAL_ANSWER\s*:\s*(.*?)\s*$",
            "flags": ["IGNORECASE", "MULTILINE"],
        },
        "parsed_option_normalization": "uppercase_option_label",
        "truncation_policy": "source_parser_ignores_finish_reason",
        "failure_types": {
            key: key
            for key in (
                "valid",
                "missing_final_answer",
                "multiple_final_answers",
                "unparseable_final_answer",
                "out_of_domain_answer",
            )
        },
        "golden_fixtures": [
            {
                "name": name,
                "text": text,
                "finish_reason": finish_reason,
                "gold_answer": gold,
                "option_labels": labels,
                "expected": {
                    "parsed_option": parsed,
                    "valid": valid,
                    "correct": correct,
                    "failure_type": failure,
                },
            }
            for name, text, finish_reason, gold, labels, parsed, valid, correct, failure in fixtures
        ],
    }


def _reference_results(reference_root: Path, seed: int) -> dict[str, Any]:
    run_root = reference_root / "runs" / V17_ID
    arms: dict[str, Any] = {}
    for arm, setting in ARM_SETTINGS.items():
        row: dict[str, Any] = {}
        for public_name, private_name in (("validation", "validation"), ("test", "test")):
            metrics = _json(
                run_root
                / private_name
                / f"seed{seed}"
                / arm
                / "evaluation_summary_private.json"
            )
            size = int(metrics["row_count"])
            row[public_name] = {
                "vote_accuracy": float(metrics["vote_accuracy"]),
                "oracle_accuracy": int(metrics["oracle_correct_count"]) / size,
            }
        row["setting_identity"] = setting
        arms[arm] = row
    return {
        "schema_version": "v17_reference_results_v1",
        "experiment_seed": seed,
        "arms": arms,
    }


def build_v17_export_spec(
    reference_root: Path,
    seed: int,
    *,
    calibration: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if seed not in V17_SEEDS:
        raise ProtocolViolation("V17 seed must be 56, 57, or 58")
    reference_root = reference_root.resolve()
    repository = verify_reference_repository(reference_root)
    experiment = reference_root / "experiments" / V17_ID
    report = reference_root / "reports" / V17_ID
    preregistration = _json(experiment / "preregistration.json")
    freeze = _json(experiment / "dataset_freeze.json")
    if (
        preregistration.get("formal_seeds") != list(V17_SEEDS)
        or preregistration.get("model") != "qwen3-14b"
        or preregistration.get("thinking") is not False
        or float(preregistration.get("solver_temperature", -1)) != 0.0
        or int(preregistration.get("solver_max_tokens", -1)) != 1800
        or int(preregistration.get("agents", -1)) != 5
        or preregistration.get("initialization_mode") != "shared_identical"
        or int(preregistration.get("train_size", -1)) != 75
        or int(preregistration.get("validation_size", -1)) != 50
        or int(preregistration.get("test_size", -1)) != 125
    ):
        raise ProtocolViolation("V17 preregistration does not match the requested baseline contract")
    split_file_names = {"opt": "opt.csv", "val": "val.csv", "test": "test.csv"}
    for frozen_name, filename in split_file_names.items():
        path = reference_root / "strict_splits_bbh_seed42" / "disambiguation_qa" / filename
        frozen = freeze["splits"][frozen_name]
        if sha256_file(path) != frozen["file_sha256"] or len(_csv_rows(path)) != int(frozen["row_count"]):
            raise ProtocolViolation(f"V17 frozen split identity mismatch: {frozen_name}")
    compute_rows = _csv_rows(report / "compute_metrics.csv")
    compute = next(
        (row for row in compute_rows if row["arm"] == "S4" and int(row["seed"]) == seed),
        None,
    )
    if compute is None:
        raise ProtocolViolation(f"V17 compute report lacks S4 Seed{seed}")
    init_path = (
        reference_root
        / "runs"
        / V17_ID
        / f"seed{seed}"
        / "_frozen_initialization"
        / "disambiguation_qa"
        / f"seed{seed}"
        / "frozen_initialization_manifest.json"
    )
    init = _json(init_path)["initialization_snapshot"]
    vector, vector_hash = _initial_vector(reference_root, seed)
    correct = sum(
        answer == str(row["answer"]).strip().strip("()").upper()
        for answer, row in zip(
            vector,
            _csv_rows(reference_root / "strict_splits_bbh_seed42" / "disambiguation_qa" / "opt.csv"),
            strict=True,
        )
    )
    if [correct] * 5 != list(init["initial_member_correct_counts"]):
        raise ProtocolViolation("V17 initial answer vector does not reconcile with frozen counts")
    formal: dict[str, Any] = {
        "status": "calibration_pending",
        "reference_arm": "V17_S4",
        "reference_training_tokens": int(compute["total_tokens"]),
        "reference_prompt_tokens": int(compute["prompt_tokens"]),
        "reference_completion_tokens": int(compute["completion_tokens"]),
        "reference_provider_calls": int(compute["provider_calls"]),
        "expected_token_budget": int(compute["total_tokens"]),
        "hard_overshoot_tolerance": 0.05,
        "hard_token_limit": int(int(compute["total_tokens"]) * 1.05),
        "reference_report_sha256": sha256_file(report / "compute_metrics.csv"),
    }
    if calibration is not None:
        caps = calibration.get("logical_eval_cap_total_by_seed", {})
        reserves = calibration.get("stop_reserve_tokens_per_member_by_seed", {})
        cap = caps.get(str(seed)) if isinstance(caps, Mapping) else None
        reserve = reserves.get(str(seed)) if isinstance(reserves, Mapping) else None
        if not isinstance(cap, int) or not isinstance(reserve, int):
            raise ProtocolViolation("calibration lacks per-seed logical cap or token reserve")
        formal.update(
            {
                "status": "frozen",
                "gepa_logical_eval_cap_total": cap,
                "stop_reserve_tokens_per_member": reserve,
                "budget_definition_version": str(calibration["budget_definition_version"]),
                "calibration_artifact_sha256": str(calibration["calibration_artifact_sha256"]),
            }
        )
    prompt_source = (
        f"runs/{V17_ID}/seed{seed}/disambiguation_qa/"
        f"shared_static_reference_seed{seed}/best_prompts.json"
    )
    prompt_values = json.loads((reference_root / prompt_source).read_text(encoding="utf-8"))
    if not isinstance(prompt_values, list) or len(prompt_values) != 5:
        raise ProtocolViolation(f"V17 S0 Seed{seed} prompt artifact is invalid")
    prompt_hashes = [hashlib.sha256(str(value).strip().encode("utf-8")).hexdigest() for value in prompt_values]
    if prompt_hashes != list(init["initial_prompt_hashes"]) or len(set(prompt_hashes)) != 1:
        raise ProtocolViolation(f"V17 Seed{seed} initial prompt parity mismatch")
    initial_prompts = [
        {"format": "json_array", "path": prompt_source, "index": index}
        for index in range(5)
    ]
    split_map = {
        "optimization": "opt.csv",
        "development": "val.csv",
        "test": "test.csv",
    }
    split_spec = {
        name: {
            "format": "csv",
            "path": f"strict_splits_bbh_seed42/disambiguation_qa/{filename}",
            "id_field": "sample_id",
            "question_field": "question",
            "gold_field": "answer",
            "question_options_format": "bbh_embedded_options",
        }
        for name, filename in split_map.items()
    }
    initial_metrics: dict[str, Any] = {
        "optimization": {
            "status": "available",
            "member_correct": [correct] * 5,
            "team_correct": correct,
            "parsed_answer_vector_hash": vector_hash,
            "reference_outcome_hash": init["initial_vote_oracle_ghm_hash"],
        }
    }
    for name, phase in (("development", "validation"), ("test", "test")):
        summary = _json(
            reference_root
            / "runs"
            / V17_ID
            / phase
            / f"seed{seed}"
            / "S0"
            / "evaluation_summary_private.json"
        )
        initial_metrics[name] = {
            "status": "available",
            "member_correct": list(summary["per_agent_correct_counts"]),
            "team_correct": int(summary["vote_correct_count"]),
        }
    model_contract = {
        "schema_version": "model_contract_v2",
        "pricing_per_million_tokens": {
            "task": {"prompt": 1.0, "completion": 4.0},
            "reflection": {"prompt": 1.0, "completion": 4.0},
        },
        "pricing_contract": {
            "currency": "CNY",
            "region_class": "china_beijing_or_us_virginia",
            "thinking": False,
            "source": "https://help.aliyun.com/zh/model-studio/qwen3-14b",
            "verified_date": "2026-08-24",
            "discounts_and_free_quota_excluded": True,
        },
        "shared_task_model": {
            "model": "qwen3-14b",
            "temperature": 0.0,
            "max_tokens": 1800,
            "timeout_seconds": 120.0,
            "max_retries": 3,
            "enable_thinking": False,
            "parser_version": "task_parser_v1",
            "output_contract_version": "task_output_contract_v1",
            "request_template_version": TASK_REQUEST_TEMPLATE_VERSION,
            "question_rendering_version": "bbh_options_marker_v1",
        },
        "independent_gepa_reflection_model": {
            "model": "qwen3-14b",
            "temperature": 0.0,
            "max_tokens": 1800,
            "timeout_seconds": 120.0,
            "max_retries": 3,
            "enable_thinking": False,
        },
        "reference_optimizer": {
            "model": "qwen3-14b",
            "roles": {
                "teacher": {"temperature": 0.4},
                "critic": {"temperature": 0.0},
                "student": {"temperature": 0.5},
            },
        },
    }
    return {
        "task": "disambiguation_qa",
        "experiment_seed": seed,
        "initial_prompts": initial_prompts,
        "splits": split_spec,
        "model_contract": {"inline": model_contract},
        "parser_contract": {"inline": _parser_contract(reference_root)},
        "budget_reference": {
            "inline": {
                "schema_version": "budget_reference_v3",
                "primary_unit": "total_model_tokens",
                "allocation_rule": "equal_floor_per_member",
                "formal": formal,
            }
        },
        "reference_results": {"inline": _reference_results(reference_root, seed)},
        "initial_metrics": initial_metrics,
        "source_identity": {
            **repository,
            "v17_execution_commit": preregistration["starting_head"],
            "v17_report_execution_commit": _json(report / "source_freeze_sanitized.json")["git_head"],
            "v17_experiment_identity": preregistration["experiment_version"],
            "dataset_manifest_sha256": freeze["manifest_sha256"],
        },
        "budget_identity": {
            "reference_arm": "V17_S4",
            "reference_report": f"reports/{V17_ID}/compute_metrics.csv",
            "budget_definition_version": formal.get("budget_definition_version", "calibration_pending"),
        },
    }
