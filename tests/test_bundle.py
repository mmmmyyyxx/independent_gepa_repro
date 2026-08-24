from __future__ import annotations

import csv

import pytest

from independent_gepa.bundle import (
    export_bundle_from_spec,
    read_json,
    validate_bundle,
    write_canonical_json,
)
from independent_gepa.final_evaluator import initial_accuracies_from_bundle
from independent_gepa.protocol import ProtocolViolation
from independent_gepa.protocol import SplitName
from tests.helpers import make_bundle


def test_bundle_validation_and_deterministic_hash(tmp_path) -> None:
    first = make_bundle(tmp_path / "one")
    second = make_bundle(tmp_path / "two")
    left = validate_bundle(first, require_formal=False)
    right = validate_bundle(second, require_formal=False)
    assert left.overall_hash == right.overall_hash
    assert [example.example_id for example in left.splits["optimization"]] == [
        "example-0",
        "example-1",
        "example-2",
    ]


def test_bundle_detects_hash_tampering(tmp_path) -> None:
    bundle = make_bundle(tmp_path)
    with (bundle / "initialization" / "agent_0.txt").open("a", encoding="utf-8") as handle:
        handle.write("tampered")
    with pytest.raises(ProtocolViolation, match="hash mismatch"):
        validate_bundle(bundle, require_formal=False)


def test_bundle_detects_split_overlap_after_valid_hash_construction(tmp_path) -> None:
    bundle = make_bundle(tmp_path, overlap=True)
    with pytest.raises(ProtocolViolation, match="split overlap"):
        validate_bundle(bundle, require_formal=False)


def test_formal_sizes_are_enforced(tmp_path) -> None:
    bundle = make_bundle(tmp_path, sizes=(75, 50, 125), total_budget=1000)
    validated = validate_bundle(bundle, require_formal=True)
    assert len(validated.splits["test"]) == 125


def test_read_only_spec_export_is_deterministic(tmp_path) -> None:
    source = make_bundle(tmp_path / "source", sizes=(75, 50, 125), total_budget=1000)
    spec = {
        "task": "disambiguation_qa",
        "experiment_seed": 56,
        "initial_prompts": [f"initialization/agent_{index}.txt" for index in range(5)],
        "splits": {
            name: f"splits/{name}.jsonl"
            for name in ("optimization", "development", "test")
        },
        "model_contract": "model_contract.json",
        "parser_contract": "parser_contract.json",
        "budget_reference": "budget_reference.json",
        "reference_results": "reference_results.json",
        "source_identity": {"commit": "opaque-source"},
        "initial_metrics": {
            "optimization": {
                "status": "available",
                "member_correct": [0] * 5,
                "team_correct": 0,
            },
            "development": {"status": "not_evaluated"},
            "test": {"status": "not_evaluated"},
        },
        "budget_identity": "opaque-budget",
    }
    spec_path = source / "export_spec.json"
    write_canonical_json(spec_path, spec)
    first_hash = export_bundle_from_spec(source, spec_path, tmp_path / "export-one")
    second_hash = export_bundle_from_spec(source, spec_path, tmp_path / "export-two")
    assert first_hash == second_hash


def _write_csv_source(root, newline: str, template_bundle) -> tuple[object, object]:
    root.mkdir(parents=True)
    write_canonical_json(root / "prompts.json", ["identical initial prompt"] * 5)
    names = ("optimization", "development", "test")
    sizes = (75, 50, 125)
    split_spec = {}
    for split_index, (name, size) in enumerate(zip(names, sizes, strict=True)):
        relative = f"{name}.csv"
        path = root / relative
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["sample_id", "question", "answer"],
                lineterminator=newline,
            )
            writer.writeheader()
            for index in range(size):
                example_id = split_index * 1000 + index
                option_count = 4 if name == "test" and index == 0 else 3
                options = newline.join(
                    f"({chr(ord('A') + option)}) choice {option}"
                    for option in range(option_count)
                )
                writer.writerow(
                    {
                        "sample_id": str(example_id),
                        "question": f"Question {example_id}{newline}Options:{newline}{options}",
                        "answer": "(A)",
                    }
                )
        split_spec[name] = {
            "path": relative,
            "format": "csv",
            "id_field": "sample_id",
            "question_field": "question",
            "gold_field": "answer",
            "question_options_format": "bbh_embedded_options",
        }
    spec = {
        "task": "disambiguation_qa",
        "experiment_seed": 56,
        "initial_prompts": [
            {"path": "prompts.json", "format": "json_array", "index": index}
            for index in range(5)
        ],
        "splits": split_spec,
        "model_contract": {
            "inline": read_json(template_bundle / "model_contract.json")
        },
        "parser_contract": {
            "inline": read_json(template_bundle / "parser_contract.json")
        },
        "budget_reference": {
            "inline": read_json(template_bundle / "budget_reference.json")
        },
        "reference_results": {
            "inline": read_json(template_bundle / "reference_results.json")
        },
        "source_identity": {"commit": "source"},
        "initial_metrics": {
            "optimization": {
                "status": "available",
                "member_correct": [60] * 5,
                "team_correct": 60,
            },
            "development": {"status": "not_evaluated"},
            "test": {"status": "not_evaluated"},
        },
        "budget_identity": "audited-pilot",
    }
    spec_path = root / "export_spec.json"
    write_canonical_json(spec_path, spec)
    return spec_path, split_spec


def test_lf_crlf_and_cr_csv_export_to_identical_canonical_splits(tmp_path) -> None:
    template = make_bundle(
        tmp_path / "template",
        sizes=(75, 50, 125),
        total_budget=1611,
    )
    exported = []
    for name, newline in (("lf", "\n"), ("crlf", "\r\n"), ("cr", "\r")):
        source = tmp_path / f"source-{name}"
        spec, _ = _write_csv_source(source, newline, template)
        output = tmp_path / f"output-{name}"
        export_bundle_from_spec(source, spec, output)
        exported.append(output)
    for split in ("optimization", "development", "test"):
        payloads = [
            (output / "splits" / f"{split}.jsonl").read_bytes()
            for output in exported
        ]
        assert payloads[0] == payloads[1] == payloads[2]
    validated = validate_bundle(exported[0], stage="pilot")
    assert len(validated.splits["optimization"][0].resolved_option_labels) == 3
    assert len(validated.splits["test"][0].resolved_option_labels) == 4
    assert len(validated.manifest["members"]) == 5
    assert len({row["prompt_hash"] for row in validated.manifest["members"]}) == 1


def test_formal_token_budget_and_logical_cap_are_frozen(tmp_path) -> None:
    bundle = make_bundle(
        tmp_path,
        sizes=(75, 50, 125),
        total_budget=1611,
    )
    validated = validate_bundle(bundle, stage="formal")
    assert validated.logical_evaluation_cap == 1611
    assert validated.token_budget()["expected_token_budget"] == 100000


def test_model_contract_preserves_reference_role_metadata(tmp_path) -> None:
    bundle = validate_bundle(make_bundle(tmp_path), require_formal=False, stage="pilot")
    roles = bundle.model_contract["reference_optimizer"]["roles"]
    assert roles["teacher"]["temperature"] == 0.4
    assert roles["critic"]["temperature"] == 0.0
    assert roles["student"]["temperature"] == 0.5


def test_not_evaluated_initial_metrics_are_valid_but_not_invented(tmp_path) -> None:
    bundle = validate_bundle(make_bundle(tmp_path), require_formal=False, stage="pilot")
    with pytest.raises(ProtocolViolation, match="were not evaluated"):
        initial_accuracies_from_bundle(bundle.manifest, SplitName.DEVELOPMENT)
