"""Verify author sources without importing their network-active module graph."""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import subprocess

from .contract import ARTIFACT_COMMIT, DSPY_COMMIT, TASKS


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def git(path: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(path), *args], text=True,
                                   encoding="utf-8").strip()


def verify_checkout(path: Path, commit: str) -> dict:
    if git(path, "rev-parse", "HEAD") != commit:
        raise ValueError("PAPER_UPSTREAM_COMMIT_MISMATCH")
    if git(path, "status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("PAPER_UPSTREAM_DIRTY")
    return {"commit": commit, "tree": git(path, "rev-parse", "HEAD^{tree}"), "clean": True}


def syntax_node(path: Path, name: str) -> ast.AST:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name:
            return node
    raise ValueError(f"AUTHOR_SYMBOL_MISSING: {name}")


def author_budgets(artifact: Path) -> dict[str, int]:
    node = syntax_node(artifact / "scripts/experiment_configs.py", "get_max_invocations")
    fn = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "author_budget", "exec"), fn)
    return {t.key: fn["get_max_invocations"](t.benchmark, t.program, "gpt-41-mini", "MIPROv2-Heavy")
            for t in TASKS}


def audit(upstream: Path) -> dict:
    artifact = upstream / "gepa-artifact"
    result = {"artifact": verify_checkout(artifact, ARTIFACT_COMMIT),
              "dspy": verify_checkout(upstream / "dspy-study", DSPY_COMMIT)}
    budgets = author_budgets(artifact)
    if budgets != {t.key: t.budget for t in TASKS}:
        raise ValueError("AUTHOR_BUDGET_DRIFT")
    launch = ast.parse((artifact / "scripts/generate_launch_commands.py").read_text())
    seeds = next(ast.literal_eval(n.value) for n in launch.body if isinstance(n, ast.Assign)
                 and any(isinstance(x, ast.Name) and x.id == "SEEDS" for x in n.targets))
    if seeds != [0]:
        raise ValueError("AUTHOR_SEEDS_DRIFT")
    configs = ast.parse((artifact / "scripts/experiment_configs.py").read_text())
    gepa_row = next(n for n in ast.walk(configs) if isinstance(n, ast.Tuple)
                    and n.elts and isinstance(n.elts[0], ast.Constant) and n.elts[0].value == "GEPA")
    init_args = next(k.value for k in gepa_row.elts[1].keywords if k.arg == "init_args")
    optimizer_args = {k.arg: ast.literal_eval(k.value) for k in init_args.keywords}
    if optimizer_args != dict(run_linearized_gepa=False, use_merge=False,
                              set_for_merge_minibatch="val", track_scores_on="val"):
        raise ValueError("AUTHOR_GEPA_MAIN_ROW_DRIFT")
    files = ["scripts/experiment_configs.py", "scripts/run_experiments.py",
             "scripts/generate_launch_commands.py", "gepa_artifact/gepa/gepa.py",
             "gepa_artifact/gepa/gepa_utils.py", "gepa_artifact/gepa/instruction_proposal.py"]
    files += [p.relative_to(artifact).as_posix() for p in
              (artifact / "gepa_artifact/benchmarks").rglob("*.py")]
    result.update(budgets=budgets, seeds=seeds, optimizer_args=optimizer_args,
                  files={p: file_hash(artifact / p) for p in sorted(set(files))})
    return result
