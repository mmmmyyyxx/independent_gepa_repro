from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_no_python_import_from_sibling_repository() -> None:
    offenders: list[str] = []
    for base in (ROOT / "src", ROOT / "scripts"):
        for path in base.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                if any(name == "multi_agent_diversity" or name.startswith("multi_dataset_diverse_rl") for name in names):
                    offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_vendor_files_are_not_part_of_root_worktree_diff() -> None:
    # The actual commit/clean check is in test_environment; this guards the
    # repository implementation from accidentally placing source files there.
    package_files = list((ROOT / "src" / "independent_gepa").glob("*.py"))
    assert package_files
    assert all((ROOT / "vendor" / "gepa") not in path.parents for path in package_files)
