from __future__ import annotations

import argparse
from pathlib import Path

from _bootstrap import ROOT  # noqa: F401

from independent_gepa.bundle import validate_bundle
from independent_gepa.parser import StrictAnswerParser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a frozen comparison bundle")
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--allow-nonformal-size", action="store_true")
    parser.add_argument(
        "--stage",
        choices=["canary", "pilot", "formal"],
        default="pilot",
        help="validate readiness for this stage; formal rejects an unfrozen formal budget",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    bundle = validate_bundle(
        args.bundle,
        require_formal=not args.allow_nonformal_size,
        stage=args.stage,
    )
    StrictAnswerParser(bundle.parser_contract).assert_golden_parity()
    print(f"PASS bundle {bundle.overall_hash}")


if __name__ == "__main__":
    main()
