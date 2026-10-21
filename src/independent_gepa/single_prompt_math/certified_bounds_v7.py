"""Retired mathematical scoring implementation. Recovery is archival only."""
from ..math_scoring import RetiredMathScorerError
def _retired(*args, **kwargs):
    raise RetiredMathScorerError('HISTORICAL_MATH_SCORER_RETIRED')
definitely_separated = _retired

if __name__ == '__main__': _retired()
