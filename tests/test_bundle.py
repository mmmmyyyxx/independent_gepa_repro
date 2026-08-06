from __future__ import annotations

import pytest

from independent_gepa.bundle import export_bundle_from_spec, validate_bundle, write_canonical_json
from independent_gepa.protocol import ProtocolViolation
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
        "experiment_seed": 46,
        "initial_prompts": [f"initialization/agent_{index}.txt" for index in range(5)],
        "splits": {
            name: f"splits/{name}.jsonl"
            for name in ("optimization", "development", "test")
        },
        "model_contract": "model_contract.json",
        "parser_contract": "parser_contract.json",
        "budget_reference": "budget_reference.json",
        "source_identity": {"commit": "opaque-source"},
        "reference_results": {
            "initial_member_accuracies": {
                "development": [0.0] * 5,
                "test": [0.0] * 5,
            }
        },
        "budget_identity": "opaque-budget",
    }
    spec_path = source / "export_spec.json"
    write_canonical_json(spec_path, spec)
    first_hash = export_bundle_from_spec(source, spec_path, tmp_path / "export-one")
    second_hash = export_bundle_from_spec(source, spec_path, tmp_path / "export-two")
    assert first_hash == second_hash
