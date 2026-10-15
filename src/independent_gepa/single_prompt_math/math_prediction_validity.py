"""Frozen prediction records; shared deterministic payload physics."""
from dataclasses import dataclass
from ..protocol import ProtocolViolation as SearchContractError
from .common import ParsedOutput
from .payload import classify_payload

@dataclass(frozen=True)
class MATHPrediction:
    """Lossless private result. Metadata survives state/cache/JSON persistence."""
    text: str | None
    finish_reason: str | None
    answer: str
    prediction_valid: bool
    invalid_reason: str | None

    def parsed(self):
        return ParsedOutput(self.answer, self.prediction_valid)

    def identity_bytes(self):
        from dataclasses import asdict
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()


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
    from dataclasses import asdict
    last=attempts[-1]
    return MATHResolvedPrediction(**asdict(last),semantic_attempt_count=len(attempts),
        raw_invalid_count=sum(not p.prediction_valid for p in attempts),
        recovered_invalid=last.prediction_valid and len(attempts)>1,
        terminal_invalid=not last.prediction_valid,transport_retry_attempts=transport_retry_attempts,
        original_predictions=attempts)
