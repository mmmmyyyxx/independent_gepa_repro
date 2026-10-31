"""Phase-scoped author-artifact runner; requires a new exact single-use grant."""
import argparse
import json
from pathlib import Path

from _bootstrap import ROOT
from independent_gepa.paper_suite.runtime import execute


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=ROOT / "runs/gepa_paper_suite_20261031")
    parser.add_argument("--authorization", required=True, type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    if not workspace.is_relative_to((ROOT / "runs").resolve()):
        raise ValueError("EXECUTION_MUST_REMAIN_IN_IGNORED_RUNS")
    result = execute(ROOT, workspace, args.authorization)
    print(json.dumps({"status": result["status"], "phase": result["phase"]}))


if __name__ == "__main__":
    main()
