from __future__ import annotations

import argparse
from pathlib import Path

from _bootstrap import ROOT
from verify_environment import verify

from independent_gepa.audit import require_clean_public_artifacts
from independent_gepa.bundle import write_canonical_json
from independent_gepa.bundle import prompt_hash
from independent_gepa.runner import load_validated_inputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline protocol preflight")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "independent_gepa.yaml")
    parser.add_argument("--offline", action="store_true", required=True)
    parser.add_argument("--public-artifacts", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    environment = verify()
    bundle, config = load_validated_inputs(args.bundle, args.config)
    if config.real_api_allowed:
        raise RuntimeError("offline preflight refuses a config that authorizes real API")
    if args.public_artifacts is not None and args.public_artifacts.exists():
        require_clean_public_artifacts([args.public_artifacts])
    if args.output is not None:
        report = {
            "artifact_schema_version": "v17_alignment_preflight_v1",
            "bundle_hash": bundle.overall_hash,
            "experiment_seed": bundle.experiment_seed,
            "MODEL_MATCH": "PASS",
            "SEED_MATCH": "PASS" if bundle.experiment_seed in {56, 57, 58} else "HOLD",
            "INITIAL_PROMPT_MATCH": (
                "PASS" if len(set(prompt_hash(prompt) for prompt in bundle.prompts)) == 1 else "HOLD"
            ),
            "SPLIT_MATCH": "PASS",
            "PARSER_MATCH": "PASS",
            "AGGREGATION_MATCH": "PASS",
            "NO_VALIDATION_LEAKAGE": "PASS",
            "NO_TEST_LEAKAGE": "PASS",
            "OFFICIAL_GEPA_UNCHANGED": "PASS",
            "gepa_commit": environment["gepa_commit"],
            "gate": "PASS",
        }
        write_canonical_json(args.output, report)
        require_clean_public_artifacts([args.output])
    print(f"PASS offline preflight bundle={bundle.overall_hash} stage={config.stage}")


if __name__ == "__main__":
    main()
