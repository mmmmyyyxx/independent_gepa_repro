from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from independent_gepa.bundle import (
    canonical_json,
    compute_overall_hash,
    prompt_hash,
    read_jsonl,
    sha256_file,
    write_canonical_json,
    write_canonical_jsonl,
)
from independent_gepa.versions import BUNDLE_VERSION, METHOD_ID


def parser_contract() -> dict[str, Any]:
    return {
        "schema_version": "parser_contract_v2",
        "source_parser_version": "task_parser_v1",
        "source_output_contract_version": "task_output_contract_v1",
        "answer_format": "option_letter",
        "parsed_option_normalization": "uppercase_option_label",
        "final_answer_line": {
            "regex": r"^\s*FINAL_ANSWER\s*:\s*(.*?)\s*$",
            "flags": ["IGNORECASE", "MULTILINE"],
        },
        "truncation_policy": "source_parser_ignores_finish_reason",
        "failure_types": {
            "valid": "valid",
            "missing_final_answer": "missing_final_answer",
            "multiple_final_answers": "multiple_final_answers",
            "unparseable_final_answer": "unparseable_final_answer",
            "out_of_domain_answer": "out_of_domain_answer",
        },
        "golden_fixtures": [
            {
                "name": "valid",
                "text": "Reasoning.\nFINAL_ANSWER: A",
                "finish_reason": "stop",
                "option_labels": ["A", "B", "C"],
                "gold_answer": "A",
                "expected": {
                    "parsed_option": "A",
                    "valid": True,
                    "correct": True,
                    "failure_type": "valid",
                },
            },
            {
                "name": "case_space_parentheses",
                "text": "  final_answer : (b)  ",
                "finish_reason": "stop",
                "option_labels": ["A", "B", "C"],
                "gold_answer": "A",
                "expected": {
                    "parsed_option": "B",
                    "valid": True,
                    "correct": False,
                    "failure_type": "valid",
                },
            },
            {
                "name": "duplicate_same",
                "text": "FINAL_ANSWER: A\nFINAL_ANSWER: A",
                "finish_reason": "stop",
                "option_labels": ["A", "B", "C"],
                "gold_answer": "A",
                "expected": {
                    "parsed_option": None,
                    "valid": False,
                    "correct": False,
                    "failure_type": "multiple_final_answers",
                },
            },
            {
                "name": "duplicate_different",
                "text": "FINAL_ANSWER: A\nFINAL_ANSWER: B",
                "finish_reason": "stop",
                "option_labels": ["A", "B", "C"],
                "gold_answer": "A",
                "expected": {
                    "parsed_option": None,
                    "valid": False,
                    "correct": False,
                    "failure_type": "multiple_final_answers",
                },
            },
            {
                "name": "out_of_range",
                "text": "FINAL_ANSWER: D",
                "finish_reason": "stop",
                "option_labels": ["A", "B", "C"],
                "gold_answer": "A",
                "expected": {
                    "parsed_option": None,
                    "valid": False,
                    "correct": False,
                    "failure_type": "out_of_domain_answer",
                },
            },
            {
                "name": "empty",
                "text": "",
                "finish_reason": "stop",
                "option_labels": ["A", "B", "C"],
                "gold_answer": "A",
                "expected": {
                    "parsed_option": None,
                    "valid": False,
                    "correct": False,
                    "failure_type": "missing_final_answer",
                },
            },
            {
                "name": "finish_reason_ignored",
                "text": "FINAL_ANSWER: A",
                "finish_reason": "length",
                "option_labels": ["A", "B", "C"],
                "gold_answer": "A",
                "expected": {
                    "parsed_option": "A",
                    "valid": True,
                    "correct": True,
                    "failure_type": "valid",
                },
            },
            {
                "name": "malformed_payload",
                "text": "FINAL_ANSWER: A because",
                "finish_reason": "stop",
                "option_labels": ["A", "B", "C"],
                "gold_answer": "A",
                "expected": {
                    "parsed_option": None,
                    "valid": False,
                    "correct": False,
                    "failure_type": "out_of_domain_answer",
                },
            },
        ],
    }


def make_bundle(
    root: Path,
    *,
    sizes: tuple[int, int, int] = (3, 2, 2),
    total_budget: int = 40,
    overlap: bool = False,
    experiment_seed: int = 56,
) -> Path:
    bundle = root / "bundle"
    bundle.mkdir(parents=True)
    prompts = ["identical initial prompt"] * 5
    for index, prompt in enumerate(prompts):
        path = bundle / "initialization" / f"agent_{index}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(prompt, encoding="utf-8", newline="\n")
    names = ("optimization", "development", "test")
    for split_index, (name, size) in enumerate(zip(names, sizes, strict=True)):
        rows = []
        for index in range(size):
            example_index = index if overlap and split_index > 0 and index == 0 else split_index * 1000 + index
            gold = chr(ord("A") + example_index % 3)
            rows.append(
                {
                    "example_id": f"example-{example_index}",
                    "question": f"Question {example_index} [gold={gold}]",
                    "choices": ["alpha", "beta", "gamma"],
                    "gold_answer": gold,
                    "option_labels": ["A", "B", "C"],
                }
            )
        write_canonical_jsonl(bundle / "splits" / f"{name}.jsonl", rows)
    transport = {
        "model": "qwen3-8b",
        "enable_thinking": False,
        "temperature": 0.0,
        "max_tokens": 128,
        "timeout_seconds": 10.0,
        "max_retries": 0,
    }
    model = {
        "schema_version": "model_contract_v3",
        "shared_task_model": {
            **transport,
            "parser_version": "task_parser_v1",
            "output_contract_version": "task_output_contract_v1",
            "request_template_version": "decision_procedure_then_mandatory_output_contract_v2",
            "question_rendering_version": "bbh_options_marker_v1",
        },
        "reference_optimizer": {
            "model": "qwen3-14b",
            "roles": {
                "teacher": {"temperature": 0.4},
                "critic": {"temperature": 0.0},
                "student": {"temperature": 0.5},
            },
        },
        "independent_gepa_evaluator_model": {
            "model": "qwen3.7-flash",
            "enable_thinking": False,
            "usage": "strict_scoring_is_deterministic_no_llm_judge",
        },
        "independent_gepa_optimizer_model": {
            **transport,
            "model": "qwen3.7-flash",
        },
        "independent_gepa_reflection_model": {
            **transport,
            "model": "qwen3.7-flash",
        },
    }
    budget = {
        "schema_version": "budget_reference_v3",
        "primary_unit": "total_model_tokens",
        "allocation_rule": "equal_floor_per_member",
        "formal": {
            "status": "frozen",
            "reference_arm": "V17_S4",
            "reference_training_tokens": 100000,
            "reference_provider_calls": 100,
            "gepa_logical_eval_cap_total": total_budget,
            "expected_token_budget": 100000,
            "hard_overshoot_tolerance": 0.05,
            "hard_token_limit": 105000,
            "stop_reserve_tokens_per_member": 1000,
            "budget_definition_version": "test-v1",
        },
    }
    reference_results = {
        "schema_version": "v17_reference_results_v1",
        "experiment_seed": experiment_seed,
        "arms": {
            arm: {
                "validation": {"vote_accuracy": 0.5, "oracle_accuracy": 0.6},
                "test": {"vote_accuracy": 0.5, "oracle_accuracy": 0.6},
            }
            for arm in ("S0", "S1", "S4")
        },
    }
    write_canonical_json(bundle / "model_contract.json", model)
    write_canonical_json(bundle / "parser_contract.json", parser_contract())
    write_canonical_json(bundle / "budget_reference.json", budget)
    write_canonical_json(bundle / "reference_results.json", reference_results)
    relative_files = {
        "model_contract.json",
        "parser_contract.json",
        "budget_reference.json",
        "reference_results.json",
        *(f"initialization/agent_{index}.txt" for index in range(5)),
        *(f"splits/{name}.jsonl" for name in names),
    }
    files = {relative: sha256_file(bundle / relative) for relative in sorted(relative_files)}
    example_ids = {
        name: [str(row["example_id"]) for row in read_jsonl(bundle / "splits" / f"{name}.jsonl")]
        for name in names
    }
    from independent_gepa.bundle import canonical_json_bytes, sha256_bytes

    example_id_hashes = {
        name: sha256_bytes(canonical_json_bytes(ids)) for name, ids in example_ids.items()
    }
    manifest = {
        "bundle_version": BUNDLE_VERSION,
        "task": "disambiguation_qa",
        "experiment_seed": experiment_seed,
        "member_count": 5,
        "members": [
            {
                "member_id": index,
                "prompt_file": f"initialization/agent_{index}.txt",
                "prompt_hash": prompt_hash(prompts[index]),
            }
            for index in range(5)
        ],
        "split_sizes": dict(zip(names, sizes, strict=True)),
        "split_hashes": {name: files[f"splits/{name}.jsonl"] for name in names},
        "split_example_id_hashes": example_id_hashes,
        "task_model": model["shared_task_model"]["model"],
        "evaluator_model": model["independent_gepa_evaluator_model"]["model"],
        "optimizer_model": model["independent_gepa_optimizer_model"]["model"],
        "reflection_model": model["independent_gepa_reflection_model"]["model"],
        "enable_thinking": False,
        "parser_version": parser_contract()["source_parser_version"],
        "voting_rule": "plurality",
        "tie_rule": "abstain",
        "initialization_mode": "shared_identical",
        "source_identity": {"commit": "opaque-source"},
        "initial_metrics": {
            "optimization": {
                "status": "available",
                "member_correct": [0] * 5,
                "team_correct": 0,
                "parsed_answer_vector_hash": "0" * 64,
            },
            "development": {"status": "not_evaluated"},
            "test": {"status": "not_evaluated"},
        },
        "split_source_provenance": {
            name: {
                "source_path": f"source/{name}.jsonl",
                "source_sha256": "0" * 64,
                "format": "jsonl",
            }
            for name in names
        },
        "budget_identity": "opaque-budget",
    }
    overall = compute_overall_hash(manifest, files)
    manifest["overall_bundle_hash"] = overall
    write_canonical_json(bundle / "manifest.json", manifest)
    write_canonical_json(
        bundle / "hashes.json",
        {
            "files": files,
            "example_ids": example_ids,
            "example_id_hashes": example_id_hashes,
            "overall_bundle_hash": overall,
        },
    )
    return bundle


def write_run_config(path: Path, *, stage: str = "offline_fake", use_merge: bool = False) -> Path:
    value = {
        "method_id": METHOD_ID,
        "stage": stage,
        "real_api_allowed": False,
        "members": 5,
        "task_model": "qwen3-8b",
        "evaluator_model": "qwen3.7-flash",
        "optimizer_model": "qwen3.7-flash",
        "reflection_model": "qwen3.7-flash",
        "provider": {
            "api_key_env": "NEVER_USED",
            "base_url_env": "NEVER_USED",
            "temperature": 0.0,
            "max_tokens": 128,
            "timeout_seconds": 10.0,
            "max_retries": 0,
            "enable_thinking": False,
        },
        "gepa": {
            "candidate_selection_strategy": "pareto",
            "frontier_type": "instance",
            "skip_perfect_score": True,
            "reflection_minibatch_size": 2,
            "perfect_score": 1.0,
            "use_merge": use_merge,
            "max_merge_invocations": 1 if use_merge else 0,
            "merge_val_overlap_floor": 1,
            "cache_evaluation": False,
            "display_progress_bar": False,
        },
    }
    path.write_text(yaml.safe_dump(value, sort_keys=True), encoding="utf-8")
    return path
