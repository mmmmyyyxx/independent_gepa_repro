"""Build an isolated Windows verification environment from pinned author sources."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

from _bootstrap import ROOT
from independent_gepa.paper_suite.contract import DSPY_COMMIT
from independent_gepa.paper_suite.sources import verify_checkout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=ROOT / "runs/gepa_paper_suite_20261031")
    parser.add_argument("--direct", action="store_true")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 11) or sys.platform != "win32":
        raise RuntimeError("THIS_ENVIRONMENT_REQUIRES_WINDOWS_PYTHON_3_11")
    base = args.workspace.resolve()
    if not base.is_relative_to((ROOT / "runs").resolve()):
        raise ValueError("ISOLATED_ENVIRONMENT_MUST_REMAIN_IN_RUNS")
    verify_checkout(base / "upstream/dspy-study", DSPY_COMMIT)
    environment = base / "venv"
    venv.EnvBuilder(with_pip=True).create(environment)
    build = base / "build/dspy-study"
    if not build.exists():
        build.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(base / "upstream/dspy-study", build,
                        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.egg-info"))
    from independent_gepa.paper_suite.sources import file_hash
    source = base / "upstream/dspy-study"
    for original in (source / "dspy").rglob("*.py"):
        copied = build / original.relative_to(source)
        if not copied.is_file() or file_hash(original) != file_hash(copied):
            raise ValueError("DSPY_BUILD_COPY_SOURCE_MISMATCH")
    # Never install PyPI dspy as a substitute for the author's modified fork.
    lock = ROOT / "requirements/paper-suite-windows.lock.txt"
    env = {k: v for k, v in os.environ.items() if not any(x in k.upper() for x in
           ["API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTHORIZATION", "BASE_URL"])}
    if args.direct:
        env = {k: v for k, v in env.items() if "PROXY" not in k.upper()}
    subprocess.run([str(environment / "Scripts/python.exe"), "-m", "pip", "--isolated", "--timeout", "120",
                    "--retries", "6", "install", "--index-url", "https://pypi.org/simple",
                    "-r", str(lock), str(build)], env=env, check=True)


if __name__ == "__main__":
    main()
