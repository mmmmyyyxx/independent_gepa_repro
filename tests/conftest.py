from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "vendor" / "gepa" / "src"):
    text = str(candidate.resolve())
    if text not in sys.path:
        sys.path.insert(0, text)


# Historical scoring implementations are archived and cannot execute as current.
_HISTORICAL_SCORE_TESTS = ['test_single_prompt_scoring_v5.py', 'test_single_prompt_scoring_v7.py', 'test_math_comparison.py', 'test_math_v4_lifecycle.py']
def pytest_ignore_collect(collection_path,config):
    return collection_path.name in _HISTORICAL_SCORE_TESTS


def pytest_collection_modifyitems(config,items):
    import json
    from pathlib import Path
    retired=json.loads((Path(__file__).parent/'historical_scoring_cases.json').read_text())
    excluded=[item for item in items if item.originalname in retired.get(item.path.name,[])]
    items[:]=[item for item in items if item not in excluded]
    if excluded:config.hook.pytest_deselected(items=excluded)
