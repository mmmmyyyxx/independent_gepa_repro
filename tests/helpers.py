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
        "version": "strict_answer_parser_contract_v1",
        "legal_options": ["A", "B", "C"],
        "accepted_patterns": [
            {
                "name": "standalone",
                "regex": r"^\s*(?P<answer>[A-Za-z])\s*$",
                "flags": ["IGNORECASE", "MULTILINE"],
            },
            {
                "name": "final_answer",
                "regex": r"\bfinal\s+answer\s*:\s*(?P<answer>[A-Za-z])\b",
                "flags": ["IGNORECASE"],
            },
        ],
        "conflict_policy": "terminal_invalid",
        "empty_policy": "terminal_invalid",
        "truncation_policy": "terminal_invalid",
        "truncation_finish_reasons": ["length"],
        "golden_fixtures": [
            {
                "name": "single",
                "text": "A",
                "finish_reason": "stop",
                "expected": {"parsed_option": "A", "valid": True, "failure_type": None},
            },
            {
                "name": "case_space",
                "text": "  b  ",
                "finish_reason": "stop",
                "expected": {"parsed_option": "B", "valid": True, "failure_type": None},
            },
            {
                "name": "explanation_final",
                "text": "Reasoning here.\nFinal answer: C",
                "finish_reason": "stop",
                "expected": {"parsed_option": "C", "valid": True, "failure_type": None},
            },
            {
                "name": "conflict",
                "text": "Final answer: A\nFinal answer: B",
                "finish_reason": "stop",
                "expected": {
                    "parsed_option": None,
                    "valid": False,
                    "failure_type": "conflicting_answers",
                },
            },
            {
                "name": "illegal",
                "text": "Final answer: Z",
                "finish_reason": "stop",
                "expected": {"parsed_option": None, "valid": False, "failure_type": "illegal_option"},
            },
            {
                "name": "empty",
                "text": "",
                "finish_reason": "stop",
                "expected": {"parsed_option": None, "valid": False, "failure_type": "empty_output"},
            },
            {
                "name": "truncated",
                "text": "Final answer: A",
                "finish_reason": "length",
                "expected": {
                    "parsed_option": None,
                    "valid": False,
                    "failure_type": "truncated_output",
                },
            },
            {
                "name": "uncertain",
                "text": "I cannot determine the answer.",
                "finish_reason": "stop",
                "expected": {
                    "parsed_option": None,
                    "valid": False,
                    "failure_type": "no_accepted_answer",
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
) -> Path:
    bundle = root / "bundle"
    bundle.mkdir(parents=True)
    prompts = [f"initial member {index}" for index in range(5)]
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
                }
            )
        write_canonical_jsonl(bundle / "splits" / f"{name}.jsonl", rows)
    model = {
        "task_model": "qwen3.7-flash-2026-07-15",
        "reflection_model": "qwen3.7-flash-2026-07-15",
        "enable_thinking": False,
        "temperature": 0.0,
        "max_tokens": 128,
        "timeout_seconds": 10.0,
        "max_retries": 1,
    }
    budget = {
        "logical_task_example_evaluations": total_budget,
        "allocation_rule": "equal_floor_per_member",
        "reference_method": {"opaque_id": "reference"},
    }
    write_canonical_json(bundle / "model_contract.json", model)
    write_canonical_json(bundle / "parser_contract.json", parser_contract())
    write_canonical_json(bundle / "budget_reference.json", budget)
    relative_files = {
        "model_contract.json",
        "parser_contract.json",
        "budget_reference.json",
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
        "experiment_seed": 46,
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
        "task_model": model["task_model"],
        "reflection_model": model["reflection_model"],
        "enable_thinking": False,
        "parser_version": parser_contract()["version"],
        "voting_rule": "plurality",
        "tie_rule": "abstain",
        "source_identity": {"commit": "opaque-source"},
        "reference_results": {
            "initial_member_accuracies": {
                "development": [0.0] * 5,
                "test": [0.0] * 5,
            }
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
        "task_model": "qwen3.7-flash-2026-07-15",
        "reflection_model": "qwen3.7-flash-2026-07-15",
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
