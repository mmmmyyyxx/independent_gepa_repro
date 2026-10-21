"""The sole current MATH correctness contract; there is no policy selector."""
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import json

CONTRACT_ID = 'cevolve_hendrycks_math_v1'
UPSTREAM_COMMIT = '985bdc1696e88e8643f081a0ff4719da39f2ae2a'
MAX_RESPONSE_CHARACTERS = 1_048_576
MAX_REFERENCE_CHARACTERS = 65_536


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=True, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('ascii')).hexdigest()


@lru_cache(maxsize=64)
def _file_hash(path, modified_ns, size):
    return sha256(Path(path).read_bytes()).hexdigest()


def contract_identity():
    base = Path(__file__).parent
    files = {}
    for name in ('contract.py', '_hendrycks.py', 'score.py', 'upstream.json'):
        path = base / name
        stat = path.stat()
        files[name] = _file_hash(str(path), stat.st_mtime_ns, stat.st_size)
    return dict(identity=CONTRACT_ID, upstream_commit=UPSTREAM_COMMIT,
        source_files=files, extraction='last_boxed_only_string_then_remove_boxed',
        comparison='Hendrycks_is_equiv_normalized_string_equality',
        normalization_exception='upstream_literal_string_equality_only',
        invalid_reference='error_never_model_score',
        missing_prediction='binary_zero_extraction_failure',
        finish_reason='metadata_only_no_extra_stop_or_truncation_gate',
        response_limit=MAX_RESPONSE_CHARACTERS, reference_limit=MAX_REFERENCE_CHARACTERS,
        symbolic_evaluator=False, policy_selection=False,
        aggregation='separate_existing_plurality_contract_not_C_EVOLVE_aggregation')


def contract_sha256():
    return digest(contract_identity())


def require_contract(value):
    if value != CONTRACT_ID:
        raise RetiredMathScorerError('RETIRED_MATH_SCORER_FRESH_CONTRACT_REQUIRED')


class RetiredMathScorerError(ValueError):
    """A frozen historical metric may not execute as the current metric."""
