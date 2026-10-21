"""Sole correctness binding in every GEPA phase."""
from ..math_scoring import CONTRACT_ID, score_math_response
IDENTITY = CONTRACT_ID
def score(prediction, reference):
    raw = prediction.get('text') if isinstance(prediction, dict) else prediction.text
    return score_math_response(raw, reference).correct
