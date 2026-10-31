"""Prepare an inactive schedule or execute an exactly authorized five-task stage."""
import argparse
import json
from pathlib import Path

from _bootstrap import ROOT
from independent_gepa.paper_suite.data import canonical
from independent_gepa.paper_suite.scheduling import execute_stage, template


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["template", "execute"])
    parser.add_argument("--workspace", type=Path, default=ROOT / "runs/gepa_paper_suite_20261031")
    parser.add_argument("--phase", choices=["search", "baseline", "final_test"])
    parser.add_argument("--grant-directory", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--plan", type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    if not workspace.is_relative_to((ROOT / "runs").resolve()):
        raise ValueError("EXECUTION_MUST_REMAIN_IN_IGNORED_RUNS")
    if args.command == "template":
        if not args.output or not args.phase:
            parser.error("template requires --phase and --output")
        plan = template(ROOT, workspace, args.phase, args.grant_directory or workspace / "pending_authorizations_v2")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as stream:
            stream.write(canonical(plan) + b"\n")
        print(json.dumps({"status": "TEMPLATE_ONLY", "READY_TO_RUN": False, "model_api_calls": 0}))
    else:
        if not args.plan:
            parser.error("execute requires --plan")
        result = execute_stage(ROOT, workspace, args.plan)
        print(json.dumps({"status": result["status"], "phase": result["phase"]}))


if __name__ == "__main__":
    main()
