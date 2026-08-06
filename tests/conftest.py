from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "vendor" / "gepa" / "src"):
    text = str(candidate.resolve())
    if text not in sys.path:
        sys.path.insert(0, text)
