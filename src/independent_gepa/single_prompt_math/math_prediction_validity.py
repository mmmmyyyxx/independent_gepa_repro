"""Current lossless prediction records; legacy persisted grades are rejected."""
from dataclasses import asdict, dataclass, field
import json
from .common import ParsedOutput
from ..protocol import ProtocolViolation as SearchContractError
from ..math_scoring import CONTRACT_ID, contract_sha256, RetiredMathScorerError
from ..math_scoring.prediction import EXTRACTION_ID, validity_contract

@dataclass(frozen=True)
class MATHPrediction:
    text: str | None
    finish_reason: str | None
    answer: str
    prediction_valid: bool
    invalid_reason: str | None
    math_scoring_contract: str = field(default=CONTRACT_ID, kw_only=True)
    math_scoring_sha256: str = field(default_factory=contract_sha256, kw_only=True)

    def __post_init__(self):
        if self.math_scoring_contract != CONTRACT_ID or self.math_scoring_sha256 != contract_sha256():
            raise SearchContractError('MATH_PREDICTION_REQUIRES_CURRENT_SCORING_CONTRACT')

    def parsed(self):
        return ParsedOutput(self.answer, self.prediction_valid)

    def identity_bytes(self):
        return json.dumps(asdict(self), sort_keys=True, separators=(',', ':')).encode()

@dataclass(frozen=True)
class MATHResolvedPrediction(MATHPrediction):
    semantic_attempt_count: int
    raw_invalid_count: int
    recovered_invalid: bool
    terminal_invalid: bool
    transport_retry_attempts: int
    original_predictions: tuple[MATHPrediction, ...]

def resolve_predictions(attempts, transport_retry_attempts=0):
    attempts=tuple(attempts)
    if (not 1 <= len(attempts) <= 4 or any(p.prediction_valid for p in attempts[:-1])
        or not attempts[-1].prediction_valid and len(attempts) != 4
        or type(transport_retry_attempts) is not int or transport_retry_attempts < 0):
        raise SearchContractError('MATH_UNRESOLVED_PREDICTION_CANNOT_BE_CACHED')
    last=attempts[-1]
    return MATHResolvedPrediction(**asdict(last), semantic_attempt_count=len(attempts),
        raw_invalid_count=sum(not p.prediction_valid for p in attempts),
        recovered_invalid=last.prediction_valid and len(attempts)>1,
        terminal_invalid=not last.prediction_valid, transport_retry_attempts=transport_retry_attempts,
        original_predictions=attempts)

def classify_payload(expression):
    # Output extraction is syntactic. It never invokes a symbolic grader.
    return None if isinstance(expression,str) else 'PREDICTION_NOT_TEXT'

def invalid_recovery_contract():
    return dict(identity='MATH_SOLVER_INVALID_RECOVERY_V1', solver_invalid_max_retries=3,
        max_semantic_attempts=4, same_request_bytes=True, first_valid_stops=True,
        transport_failures_consume_semantic_attempt=False, terminal_requires_completed_invalid_attempts=4,
        terminal_invalid='incorrect_continue_no_vote', logical_evaluation_count=1,
        cache='resolved_valid_or_exhausted_terminal_only', invalidity_weight='none')

def structured_recovery_contract():
    return {**invalid_recovery_contract(), 'identity':'MATH_HENDRYCKS_BOXED_INVALID_RECOVERY_V1',
        'same_request_bytes':False, 'same_messages_and_sampling':True,
        'capacity_policy':'STRUCTURED_SOLVER_CAPACITY_EXECUTION_V2',
        'answer_extraction':EXTRACTION_ID, 'retry_trigger':'extraction_failure_never_correctness'}
