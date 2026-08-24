from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from _bootstrap import ROOT

from independent_gepa.reporting import build_v17_report, load_v17_bundles


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build sanitized V17 Independent-GEPA report")
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--reference-root", type=Path, default=ROOT.parent / "multi_agent_diversity"
    )
    return parser


def _head(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def main() -> None:
    args = build_parser().parse_args()
    result = build_v17_report(
        bundles=load_v17_bundles(args.bundle_root),
        run_root=args.run_root,
        output=args.output,
        repository_commit=_head(ROOT),
        reference_commit=_head(args.reference_root),
    )
    print(f"PASS report decision={result['decision_label']}")


if __name__ == "__main__":
    main()
