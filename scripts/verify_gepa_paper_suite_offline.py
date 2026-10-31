"""Credential-free verification; Windows spawn children inherit socket denial."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from _bootstrap import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["pytest", "integration", "compile", "data", "cli"])
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--workspace", type=Path, default=ROOT / "runs/gepa_paper_suite_20261031")
    args, rest = parser.parse_known_args()
    if rest and rest[0] == "--":
        rest = rest[1:]
    guard = args.workspace / "verification" / uuid.uuid4().hex
    guard.mkdir(parents=True)
    shutil.copyfile(ROOT / "tests/paper_zero_network/sitecustomize.py", guard / "sitecustomize.py")
    events = guard / "events.txt"
    env = {k: v for k, v in os.environ.items() if not any(marker in k.upper() for marker in
           ["API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTHORIZATION", "BASE_URL"])}
    env.update(PYTHONPATH=os.pathsep.join([str(guard.resolve()), str(ROOT / "src"), str(ROOT / "vendor/gepa/src")]),
               PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PAPER_OFFLINE_EVENTS=str(events.resolve()),
               LITELLM_LOCAL_MODEL_COST_MAP="True", WANDB_MODE="offline",
               HF_HUB_OFFLINE="1", HF_DATASETS_OFFLINE="1", DO_NOT_TRACK="1",
               DSPY_CACHEDIR=str((guard / "dspy_cache").resolve()),
               NLTK_DATA=str((args.workspace / "nlp/nltk_data").resolve()))
    if args.mode == "pytest":
        command = [str(args.python), "-m", "pytest", *rest]
    elif args.mode == "compile":
        command = [str(args.python), "-m", "compileall", "-q", "src", "scripts", *rest]
    elif args.mode == "data":
        command = [str(args.python), str(ROOT / "scripts/prepare_gepa_paper_suite.py"), "data-bundle",
                   "--workspace", str(args.workspace.resolve()), *rest]
    elif args.mode == "cli":
        allowed = {"prepare_gepa_paper_suite.py", "fetch_gepa_paper_sources.py", "setup_gepa_paper_environment.py",
                   "prepare_gepa_paper_nlp.py", "prepare_gepa_paper_retriever.py", "run_gepa_paper_suite.py",
                   "run_gepa_paper_schedule.py"}
        script = (ROOT / rest[0]).resolve() if rest else None
        if script is None or script.parent != ROOT / "scripts" or script.name not in allowed:
            raise ValueError("PAPER_VERIFICATION_CLI_NOT_ALLOWED")
        command = [str(args.python), str(script), *rest[1:]]
    else:
        command = [str(args.python), "-m", "independent_gepa.paper_suite.offline",
                   "--workspace", str(args.workspace.resolve()), *rest]
    result = subprocess.run(command, cwd=ROOT, env=env)
    attempts = len(events.read_text().splitlines()) if events.exists() else 0
    receipt = {"network_attempt_count_all_children": attempts, "model_api_calls": 0,
               "credentials_removed": True, "returncode": result.returncode}
    (guard / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))
    raise SystemExit(result.returncode or bool(attempts))


if __name__ == "__main__":
    main()
