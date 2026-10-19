"""V6 all-phase binding to the unchanged V5 mathematical algorithm.

The legacy policy identifies the exact numerical algorithm, not authorization to
execute a phase. V6's separately frozen config/protocol supplies the wider scope.
"""
from functools import lru_cache
from pathlib import Path

from .scoring_v5 import load_policy, score as score_v5

IDENTITY = 'V5_EXACT_SCORING_ALL_PHASES_V6'


@lru_cache(maxsize=1)
def algorithm_policy():
    return load_policy(Path(__file__).resolve().parents[3])


def score(prediction, reference):
    return score_v5(prediction, reference, policy=algorithm_policy())
