"""Derive a new-model bundle without changing frozen experimental inputs."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .bundle import export_bundle_from_spec, validate_bundle, write_canonical_json
from .model_profile import MODEL_PROFILE_ID, split_role_model_contract


def build_model_variant_spec(source_bundle: Path) -> dict[str, Any]:
    """Build a data-only spec that changes only active model identities.

    Initial outcomes from the prior solver are deliberately not carried over as
    metrics for the new solver. Prompts, splits, parser, budget, and reference
    results remain byte-for-byte source inputs to the generic bundle exporter.
    """

    source = validate_bundle(source_bundle, require_formal=True, stage=None)
    return {
        "task": source.manifest["task"],
        "experiment_seed": source.experiment_seed,
        "initial_prompts": [
            f"initialization/agent_{member_id}.txt" for member_id in range(5)
        ],
        "splits": {
            name: f"splits/{name}.jsonl"
            for name in ("optimization", "development", "test")
        },
        "model_contract": {"inline": split_role_model_contract()},
        "parser_contract": "parser_contract.json",
        "budget_reference": "budget_reference.json",
        "reference_results": "reference_results.json",
        "source_identity": {
            "derivation": "active_model_profile_only",
            "model_profile_id": MODEL_PROFILE_ID,
            "parent_bundle_hash": source.overall_hash,
            "parent_source_identity": source.manifest["source_identity"],
            "historical_initial_metrics_model": source.manifest["task_model"],
            "active_initial_metrics_status": "not_evaluated_after_solver_change",
        },
        "initial_metrics": {
            name: {"status": "not_evaluated"}
            for name in ("optimization", "development", "test")
        },
        "budget_identity": source.manifest["budget_identity"],
    }


def export_model_variant_bundle(source_bundle: Path, output: Path) -> str:
    """Export and validate a split-role model variant of a frozen bundle."""

    source_bundle = source_bundle.resolve()
    spec = build_model_variant_spec(source_bundle)
    with TemporaryDirectory(prefix="independent_gepa_model_variant_") as temp_dir:
        spec_path = Path(temp_dir) / "export_spec.json"
        write_canonical_json(spec_path, spec)
        return export_bundle_from_spec(source_bundle, spec_path, output)
