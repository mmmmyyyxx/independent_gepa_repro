"""Gold-blind boxed extraction and pinned Hendrycks finite string comparison."""
from dataclasses import asdict, dataclass
from functools import lru_cache
from . import _hendrycks as upstream
from .contract import (CONTRACT_ID, MAX_REFERENCE_CHARACTERS,
    MAX_RESPONSE_CHARACTERS, contract_sha256, digest)


class InvalidGroundTruthError(ValueError):
    pass


class MathScoringInputError(ValueError):
    """Serialization or resource failure; never implicitly scored as wrong."""


def extract_final_answer(raw_response):
    if raw_response is None:
        return None
    if not isinstance(raw_response, str):
        raise MathScoringInputError('PREDICTION_NOT_TEXT')
    if len(raw_response) > MAX_RESPONSE_CHARACTERS:
        raise MathScoringInputError('PREDICTION_RESOURCE_LIMIT')
    return upstream.remove_boxed(upstream.last_boxed_only_string(raw_response))


def prepare_ground_truth(ground_truth):
    if not isinstance(ground_truth, str) or not ground_truth.strip():
        raise InvalidGroundTruthError('MISSING_OR_NON_TEXT_GROUND_TRUTH')
    if len(ground_truth) > MAX_REFERENCE_CHARACTERS:
        raise InvalidGroundTruthError('GROUND_TRUTH_RESOURCE_LIMIT')
    value = ground_truth
    if r'\boxed' in value or r'\fbox' in value:
        value = extract_final_answer(value)
        if value is None:
            raise InvalidGroundTruthError('GROUND_TRUTH_BOX_EXTRACTION_FAILURE')
    try:
        normalized = upstream._strip_string(value)
    except Exception as exc:
        raise InvalidGroundTruthError('GROUND_TRUTH_NORMALIZATION_FAILURE') from exc
    if not normalized.strip():
        raise InvalidGroundTruthError('EMPTY_NORMALIZED_GROUND_TRUTH')
    return value, normalized


@dataclass(frozen=True)
class MathScoreResult:
    correct: bool
    extracted_answer: str | None
    normalized_prediction: str | None
    normalized_ground_truth: str
    reason: str
    contract_sha256: str
    input_sha256: str
    normalization_error: str | None = None
    scoring_contract: str = CONTRACT_ID

    def __post_init__(self):
        if type(self.correct) is not bool or self.scoring_contract != CONTRACT_ID:
            raise ValueError('MATH_SCORE_CONTRACT_INVALID')

    @property
    def score(self):
        return int(self.correct)

    @property
    def prediction_valid(self):
        return self.extracted_answer is not None

    def to_dict(self):
        return dict(**asdict(self), score=self.score,
            prediction_valid=self.prediction_valid)


@lru_cache(maxsize=8192)
def _score_cached(raw_response, ground_truth, identity):
    gold, gold_normalized = prepare_ground_truth(ground_truth)
    prediction = extract_final_answer(raw_response)
    input_id = digest(dict(contract=identity, response=raw_response, reference=ground_truth))
    if prediction is None:
        return MathScoreResult(False, None, None, gold_normalized,
            'extraction_failure', identity, input_id)
    try:
        normalized = upstream._strip_string(prediction)
    except Exception as exc:
        # This is exactly the upstream is_equiv exception semantics. It is not
        # another scorer or an approximate mathematical-equivalence fallback.
        return MathScoreResult(bool(upstream.is_equiv(prediction, gold)), prediction,
            None, gold_normalized, 'normalization_exception_literal_comparison',
            identity, input_id, type(exc).__name__)
    correct = bool(upstream.is_equiv(prediction, gold))
    assert correct == (normalized == gold_normalized)
    return MathScoreResult(correct, prediction, normalized, gold_normalized,
        'normalized_match' if correct else 'normalized_mismatch', identity, input_id)


def score_math_response(raw_response, ground_truth):
    """The sole correctness entrypoint. Gold validity is checked even with no output."""
    if raw_response is not None and not isinstance(raw_response, str):
        raise MathScoringInputError('PREDICTION_NOT_TEXT')
    if raw_response is not None and len(raw_response) > MAX_RESPONSE_CHARACTERS:
        raise MathScoringInputError('PREDICTION_RESOURCE_LIMIT')
    # Validate non-text references before entering an argument-hashed cache.
    if not isinstance(ground_truth, str):
        raise InvalidGroundTruthError('MISSING_OR_NON_TEXT_GROUND_TRUTH')
    return _score_cached(raw_response, ground_truth, contract_sha256())


def score_parsed_answer(answer, valid, ground_truth):
    """Typed parser adapter; correctness still uses the sole raw-response scorer."""
    if type(valid) is not bool or not isinstance(answer, str):
        raise MathScoringInputError('PARSED_PREDICTION_INVALID')
    return score_math_response(r'\boxed{' + answer + '}' if valid else '', ground_truth)


def normalization(value):
    """Expose the pinned helper for parity diagnostics, never an alternate scorer."""
    return upstream._strip_string(value)
