"""Offline commands only. This entrypoint cannot launch models or experiments."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import ROOT
from independent_gepa.paper_suite.contract import draft
from independent_gepa.paper_suite.data import canonical, write_bundle
from independent_gepa.paper_suite.sources import audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["source-audit", "draft", "data-bundle", "run-pack"])
    parser.add_argument("--workspace", type=Path, default=ROOT / "runs/gepa_paper_suite_20261031")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--environment-python", type=Path)
    parser.add_argument("--deployment-presence", type=Path)
    args = parser.parse_args()
    if args.command == "run-pack":
        from independent_gepa.paper_suite.preparation import write_run_pack
        presence = json.loads(args.deployment_presence.read_text()) if args.deployment_presence else None
        result = write_run_pack(ROOT, args.workspace.resolve(), args.output,
                                args.environment_python or args.workspace / "venv/Scripts/python.exe", presence)
        print(json.dumps({"status": "LAUNCH_PACK_PREPARED_NOT_AUTHORIZED", "READY_TO_RUN": False,
                          "data_rows_verified": result["data"]["rows"], "API_CALLS": 0}))
        return
    if args.command == "data-bundle":
        receipt = write_bundle(args.workspace / "upstream/gepa-artifact",
                               args.workspace / "assets", args.output)
        print(json.dumps({"status": "DATA_PREPARED", "tasks": list(receipt["splits"]), "API_CALLS": 0}))
        return
    result = audit(args.workspace / "upstream") if args.command == "source-audit" else draft()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as f:
        f.write(canonical(result) + b"\n")
    print(json.dumps({"status": "PREPARED_NOT_AUTHORIZED", "API_CALLS": 0}))


if __name__ == "__main__":
    main()
