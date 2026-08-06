"""Resolve the pinned vendored GEPA checkout without relying on site packages."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def vendor_gepa_src() -> Path:
    return (repository_root() / "vendor" / "gepa" / "src").resolve()


def import_vendor_gepa() -> object:
    source = vendor_gepa_src()
    if not source.is_dir():
        raise RuntimeError(f"pinned GEPA source directory is missing: {source}")
    source_text = str(source)
    if source_text not in sys.path:
        sys.path.insert(0, source_text)
    module = importlib.import_module("gepa")
    resolved = Path(module.__file__).resolve()
    if source not in resolved.parents:
        raise RuntimeError(f"gepa resolved outside vendor checkout: {resolved}")
    return module
