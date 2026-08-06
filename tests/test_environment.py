from __future__ import annotations

import subprocess
from pathlib import Path

from independent_gepa._vendor import import_vendor_gepa, vendor_gepa_src
from independent_gepa.versions import GEPA_COMMIT, GEPA_TAG

ROOT = Path(__file__).resolve().parents[1]


def test_pinned_gepa_commit_clean_and_import_path() -> None:
    vendor = ROOT / "vendor" / "gepa"
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=vendor, check=True, capture_output=True, text=True
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--short"], cwd=vendor, check=True, capture_output=True, text=True
    ).stdout.strip()
    tag_commit = subprocess.run(
        ["git", "rev-list", "-n", "1", GEPA_TAG],
        cwd=vendor,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert head == GEPA_COMMIT
    assert tag_commit == GEPA_COMMIT
    assert status == ""
    gepa = import_vendor_gepa()
    assert vendor_gepa_src() in Path(gepa.__file__).resolve().parents
