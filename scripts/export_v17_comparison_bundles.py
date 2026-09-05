from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import ROOT

from independent_gepa.bundle import export_bundle_from_spec, write_canonical_json
from independent_gepa.v17 import V17_SEEDS, build_v17_export_spec


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only export of V17 Seed56-58 bundles")
    parser.add_argument(
        "--source-root", type=Path, default=ROOT.parent / "multi_agent_diversity"
    )
    parser.add_argument("--spec-output-root", type=Path, required=True)
    parser.add_argument("--bundle-output-root", type=Path, required=True)
    parser.add_argument("--calibration", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    calibration = None
    if args.calibration is not None:
        calibration = json.loads(args.calibration.read_text(encoding="utf-8"))
    for seed in V17_SEEDS:
        spec = build_v17_export_spec(args.source_root, seed, calibration=calibration)
        spec_path = args.spec_output_root / f"seed{seed}_export_spec.json"
        write_canonical_json(spec_path, spec)
        bundle_path = (
            args.bundle_output_root
            / f"disambiguation_qa_v17_seed{seed}_qwen3_8b_flash_v1"
        )
        digest = export_bundle_from_spec(args.source_root, spec_path, bundle_path)
        print(f"PASS Seed{seed} bundle={digest}")


if __name__ == "__main__":
    main()
