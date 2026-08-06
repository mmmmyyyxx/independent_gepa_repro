from __future__ import annotations

import argparse
from pathlib import Path

from _bootstrap import ROOT
from verify_environment import verify

from independent_gepa.audit import require_clean_public_artifacts
from independent_gepa.runner import load_validated_inputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline protocol preflight")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "independent_gepa.yaml")
    parser.add_argument("--offline", action="store_true", required=True)
    parser.add_argument("--public-artifacts", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    verify()
    bundle, config = load_validated_inputs(args.bundle, args.config)
    if config.real_api_allowed:
        raise RuntimeError("offline preflight refuses a config that authorizes real API")
    if args.public_artifacts is not None and args.public_artifacts.exists():
        require_clean_public_artifacts([args.public_artifacts])
    print(f"PASS offline preflight bundle={bundle.overall_hash} stage={config.stage}")


if __name__ == "__main__":
    main()
