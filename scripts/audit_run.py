from __future__ import annotations

import argparse
from pathlib import Path

from _bootstrap import ROOT  # noqa: F401

from independent_gepa.audit import audit_public_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit sanitized public run artifacts")
    parser.add_argument("paths", nargs="+", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    findings = audit_public_paths(args.paths)
    if findings:
        for finding in findings:
            print(f"HOLD {finding.path}: {finding.reason}")
        raise SystemExit(1)
    print("PASS public artifact leakage audit")


if __name__ == "__main__":
    main()
