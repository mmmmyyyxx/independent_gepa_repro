from __future__ import annotations

import argparse
from pathlib import Path

from _bootstrap import ROOT  # noqa: F401

from independent_gepa.model_variant import export_model_variant_bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Derive a frozen bundle with qwen3-8b solver and qwen3.7-flash "
            "evaluator/optimizer/reflection while preserving all non-model inputs"
        )
    )
    parser.add_argument("--source-bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    digest = export_model_variant_bundle(args.source_bundle, args.output)
    print(f"PASS model-variant bundle exported with overall hash {digest}")


if __name__ == "__main__":
    main()
