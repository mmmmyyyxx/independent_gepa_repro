from __future__ import annotations

import argparse
from pathlib import Path

from _bootstrap import ROOT

from independent_gepa.bundle import export_bundle_from_spec


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="One-time read-only export of a frozen prompt-team comparison bundle"
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=ROOT.parent / "multi_agent_diversity",
        help="read-only source repository root",
    )
    parser.add_argument("--spec", type=Path, required=True, help="data-only export specification")
    parser.add_argument("--output", type=Path, required=True, help="new or empty bundle directory")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    digest = export_bundle_from_spec(args.source_root, args.spec, args.output)
    print(f"PASS bundle exported with overall hash {digest}")


if __name__ == "__main__":
    main()
