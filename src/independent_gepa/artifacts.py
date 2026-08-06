"""Private artifact writing and public sanitization."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

from .bundle import prompt_hash, write_canonical_json
from .protocol import ProtocolViolation


def write_private_json(path: Path, value: Any) -> None:
    if "runs" not in {part.lower() for part in path.resolve().parts}:
        raise ProtocolViolation("full private artifacts may be written only under a runs directory")
    write_canonical_json(path, value)


def prompt_identity_rows(prompts: Sequence[str]) -> list[dict[str, Any]]:
    return [
        {"member_id": index, "prompt_hash": prompt_hash(prompt)}
        for index, prompt in enumerate(prompts)
    ]


def sanitize_member_results(
    *,
    bundle_hash: str,
    experiment_seed: int,
    prompts: Sequence[str],
    member_rows: Sequence[Mapping[str, Any]],
    budget: Mapping[str, Any],
    provider_accounting: Mapping[str, Any],
    wall_clock_seconds: float,
) -> dict[str, Any]:
    safe_rows = []
    for index, row in enumerate(member_rows):
        safe_rows.append(
            {
                "member_id": index,
                "gepa_seed": int(row["gepa_seed"]),
                "best_prompt_hash": prompt_hash(prompts[index]),
                "initial_prompt_hash": str(row["initial_prompt_hash"]),
                "candidate_count": int(row["candidate_count"]),
                "logical_evaluations": int(row["logical_evaluations"]),
                "completed": bool(row["completed"]),
            }
        )
    return {
        "artifact_schema_version": "independent_gepa_public_run_summary_v1",
        "bundle_hash": bundle_hash,
        "experiment_seed": experiment_seed,
        "members": safe_rows,
        "final_team": prompt_identity_rows(prompts),
        "budget": dict(budget),
        "provider_accounting": dict(provider_accounting),
        "wall_clock_seconds": float(wall_clock_seconds),
        "audit_status": "pending",
    }


def stable_config_hash(config: Mapping[str, Any]) -> str:
    from .bundle import canonical_json

    return hashlib.sha256(canonical_json(dict(config)).encode("utf-8")).hexdigest()
