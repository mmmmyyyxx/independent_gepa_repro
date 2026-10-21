"""Historical module path; a thin adapter to the sole current boxed scorer."""
from dataclasses import asdict
import json
from .common import ParsedOutput
from ..protocol import ProtocolViolation as SearchContractError
from ..math_scoring import extract_final_answer, normalization
from ..math_scoring.prediction import (EXTRACTION_ID as IDENTITY, VALIDITY_ID as VALIDITY,
    extraction_contract, validity_contract, extract_answer)
from .math_prediction_validity import MATHPrediction, MATHResolvedPrediction, resolve_predictions

POLICY=extraction_contract()
LABEL=r'\boxed{'
normalize_payload=normalization

def classify_prediction(text, finish_reason='stop'):
    expression, reason=extract_answer(text)
    return MATHPrediction(text,finish_reason,expression,reason is None,reason)

def prediction_from_persisted(value):
    data=asdict(value) if isinstance(value,(MATHPrediction,MATHResolvedPrediction)) else value
    if not isinstance(data,dict):raise SearchContractError('MATH_PREDICTION_STATE_INVALID')
    if set(data)==set(MATHResolvedPrediction.__dataclass_fields__):
        expected=resolve_predictions(tuple(prediction_from_persisted(p) for p in data['original_predictions']),data['transport_retry_attempts'])
    elif set(data)==set(MATHPrediction.__dataclass_fields__):
        expected=classify_prediction(data['text'],data['finish_reason'])
    else:raise SearchContractError('HISTORICAL_MATH_CACHE_REQUIRES_FRESH_SCORING_IDENTITY')
    if json.dumps(data,sort_keys=True)!=json.dumps(asdict(expected),sort_keys=True):
        raise SearchContractError('MATH_PREDICTION_STATE_CORRUPTION')
    return expected

def boundaries(raw):
    # Used only to segment ordinary optimizer evidence, never for correctness.
    answer=extract_final_answer(raw)
    if answer is None:return []
    start=raw.rfind(r'\boxed')
    return [('boxed',start,len(raw),True)]
