from __future__ import annotations

import pytest

from independent_gepa.artifacts import sanitize_member_results, write_private_json
from independent_gepa.audit import audit_value, require_clean_public_artifacts
from independent_gepa.bundle import write_canonical_json
from independent_gepa.protocol import ProtocolViolation


def test_sanitized_summary_contains_hashes_not_prompts() -> None:
    prompts = [f"secret prompt {index}" for index in range(5)]
    rows = [
        {
            "gepa_seed": 46000 + index,
            "initial_prompt_hash": f"initial-{index}",
            "candidate_count": 2,
            "logical_evaluations": 8,
            "completed": True,
        }
        for index in range(5)
    ]
    summary = sanitize_member_results(
        bundle_hash="bundle",
        experiment_seed=46,
        prompts=prompts,
        member_rows=rows,
        budget={"consumed_total": 40},
        provider_accounting={"real_requests": 10},
        wall_clock_seconds=1.0,
    )
    serialized = str(summary)
    assert "secret prompt" not in serialized
    assert not audit_value(summary)


def test_public_leakage_audit_detects_content_and_paths(tmp_path) -> None:
    unsafe = tmp_path / "unsafe.json"
    write_canonical_json(
        unsafe,
        {"system_prompt": "full prompt", "where": r"D:\private\runs", "token": "sk-1234567890123456"},
    )
    with pytest.raises(ProtocolViolation, match="leakage"):
        require_clean_public_artifacts([unsafe])


def test_private_artifact_boundary(tmp_path) -> None:
    write_private_json(tmp_path / "runs" / "member_0" / "private.json", {"system_prompt": "allowed privately"})
    with pytest.raises(ProtocolViolation, match="runs"):
        write_private_json(tmp_path / "reports" / "private.json", {"system_prompt": "not allowed"})
