"""Retired historical scoring continuations: archival recovery only."""
from ..math_scoring import RetiredMathScorerError

def _retired(*args, **kwargs):
    raise RetiredMathScorerError('HISTORICAL_SCORING_CONTINUATION_RETIRED_NEW_FREEZE_REQUIRED')

scoring_module = _retired
policy_version = _retired
load_policy = _retired
recovery_config = _retired
score = _retired
inventory = _retired
append_event = _retired
request_key = _retired
test_record = _retired
prepare = _retired
freeze = _retired
restore_runtime = _retired
finish_test_profile = _retired
execute = _retired
publish = _retired

class TestContinuationRuntime:
    __init__ = _retired
