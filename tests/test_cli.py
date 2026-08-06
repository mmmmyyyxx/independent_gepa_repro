from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [
    "verify_environment.py",
    "export_comparison_bundle.py",
    "validate_comparison_bundle.py",
    "preflight.py",
    "run_independent_gepa.py",
    "evaluate_final_team.py",
    "audit_run.py",
]


@pytest.mark.parametrize("script", SCRIPTS)
def test_cli_help(script: str) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()
