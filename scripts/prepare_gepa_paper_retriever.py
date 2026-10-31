"""Prepare the original BM25 resource offline; --index waits for sufficient RAM."""
import argparse
import json
from pathlib import Path

from _bootstrap import ROOT
from independent_gepa.paper_suite.retrieval import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=ROOT / "runs/gepa_paper_suite_20261031")
    parser.add_argument("--index", action="store_true")
    parser.add_argument("--minimum-free-gib", type=float, default=8.0)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    if not workspace.is_relative_to((ROOT / "runs").resolve()):
        raise ValueError("RETRIEVAL_RESOURCES_MUST_REMAIN_IN_IGNORED_RUNS")
    result = prepare(workspace, build_index=args.index, minimum_free_gib=args.minimum_free_gib)
    print(json.dumps({"index_ready": result["index_ready"], "MODEL_API_CALLS": 0}))


if __name__ == "__main__":
    main()
