"""Current extraction validity does not invoke a mathematical parser."""
from ..math_scoring import MathScoringInputError
def classify_payload(expression):
    if not isinstance(expression,str):raise MathScoringInputError('PREDICTION_NOT_TEXT')
    return None
