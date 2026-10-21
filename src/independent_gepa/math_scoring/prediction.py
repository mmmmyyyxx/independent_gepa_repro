"""Fixed extraction/validity metadata shared by all MATH adapters."""
from .contract import CONTRACT_ID, contract_sha256, MAX_RESPONSE_CHARACTERS
from .score import extract_final_answer

EXTRACTION_ID = CONTRACT_ID + '/last_boxed'
VALIDITY_ID = CONTRACT_ID + '/extraction_validity'


def extraction_contract():
    return dict(identity=EXTRACTION_ID, math_scoring_contract=CONTRACT_ID,
        source='hendrycks/math@985bdc1696e88e8643f081a0ff4719da39f2ae2a',
        selection='last_boxed_preferred_else_last_fbox_then_upstream_remove_boxed',
        fbox='original_remove_boxed_rejects_fbox', gold_access=False,
        unboxed_fallback=False, final_answer_label_fallback=False,
        mathematical_parser=False, maximum_raw_characters=MAX_RESPONSE_CHARACTERS)


def validity_contract():
    return dict(identity=VALIDITY_ID, math_scoring_contract=CONTRACT_ID,
        reference_failure='hard_contract_failure',
        prediction_failure='extraction_failure_binary_zero',
        finish_reason='retained_metadata_no_extra_scoring_gate',
        invalid_response_retries=3, fallback_extraction=False,
        invalid_vote='excluded_from_equivalence_classes', denominator='all_frozen_examples',
        invalidity_telemetry='observation_only', answer_extraction=extraction_contract())


def extract_answer(text):
    answer = extract_final_answer(text)
    return (answer, None) if answer is not None else ('', 'extraction_failure')


def cache_identity():
    return dict(math_scoring_contract=CONTRACT_ID, math_scoring_sha256=contract_sha256())
