"""Phase-scoped author-artifact runner; requires a new exact single-use grant."""
import argparse
import json
import os
from pathlib import Path
import time

from _bootstrap import ROOT
from independent_gepa.paper_suite.runtime import execute
from independent_gepa.paper_suite.sources import file_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=ROOT / "runs/gepa_paper_suite_20261031")
    parser.add_argument("--authorization", required=True, type=Path)
    parser.add_argument("--dispatch-ready", type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    if not workspace.is_relative_to((ROOT / "runs").resolve()):
        raise ValueError("EXECUTION_MUST_REMAIN_IN_IGNORED_RUNS")
    if args.dispatch_ready:
        ready = args.dispatch_ready.resolve()
        if not ready.is_relative_to(workspace):
            raise ValueError("DISPATCH_MARKER_MUST_BE_IN_WORKSPACE")
        request = ready.with_suffix(".request.json")
        temporary = ready.with_suffix(".request.partial")
        with temporary.open("xb") as stream:
            stream.write(json.dumps({"pid": os.getpid(), "authorization_sha256": file_hash(args.authorization)}).encode())
        temporary.replace(request)
        deadline = time.monotonic() + 30
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(.05)
        marker = json.loads(ready.read_text(encoding="utf-8"))
        if marker != {"pid": os.getpid(), "authorization_sha256": file_hash(args.authorization)}:
            raise ValueError("DISPATCH_MARKER_IDENTITY_MISMATCH")
    result = execute(ROOT, workspace, args.authorization)
    print(json.dumps({"status": result["status"], "phase": result["phase"]}))


if __name__ == "__main__":
    main()
