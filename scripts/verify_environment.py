from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from _bootstrap import ROOT

from independent_gepa._vendor import import_vendor_gepa, vendor_gepa_src
from independent_gepa.versions import GEPA_COMMIT, GEPA_TAG


def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def verify() -> dict[str, str]:
    vendor = ROOT / "vendor" / "gepa"
    if not vendor.is_dir():
        raise RuntimeError("vendor/gepa is missing")
    head = _git("rev-parse", "HEAD", cwd=vendor)
    if head != GEPA_COMMIT:
        raise RuntimeError(f"GEPA HEAD mismatch: {head}")
    tag_commit = _git("rev-list", "-n", "1", GEPA_TAG, cwd=vendor)
    if tag_commit != GEPA_COMMIT:
        raise RuntimeError(f"GEPA tag {GEPA_TAG} does not resolve to the pinned commit")
    status = _git("status", "--short", cwd=vendor)
    if status:
        raise RuntimeError("vendor/gepa working tree is dirty")
    module = import_vendor_gepa()
    imported = Path(module.__file__).resolve()
    expected = vendor_gepa_src()
    if expected not in imported.parents:
        raise RuntimeError(f"gepa imported from unexpected path: {imported}")
    return {
        "gepa_commit": head,
        "gepa_tag": GEPA_TAG,
        "gepa_import": str(imported),
        "vendor_status": "clean",
    }


def main() -> None:
    argparse.ArgumentParser(description="Verify pinned GEPA identity and import path").parse_args()
    result = verify()
    print(f"PASS GEPA tag {result['gepa_tag']} commit {result['gepa_commit']}")
    print(f"PASS GEPA import {result['gepa_import']}")
    print("PASS vendor/gepa working tree clean")


if __name__ == "__main__":
    main()
