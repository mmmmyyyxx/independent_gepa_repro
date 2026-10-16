"""Explicit V5 scoring policy and local-process contract for Test continuation."""
from functools import lru_cache
import json
from pathlib import Path
import subprocess
import sys
import yaml

from ..protocol import ProtocolViolation
from ..math_comparison.benchmark import worker_environment
from .common import digest
from .math_domain_v2 import current_worker_deadline
from .recovery import temporary_worker_exit,temporary_worker_resource_error

POLICY_PATH='configs/gepa_single_prompt_scoring_continuation_v5.yaml'


def load_policy(root: Path):
    policy=yaml.safe_load((root/POLICY_PATH).read_text(encoding='utf-8'))
    validate_policy(policy);return policy


def validate_policy(policy):
    expected=dict(identity='GEPA_SCORING_CONTINUATION_V5',interval_precision_bits=64,
        interval_max_nodes=256,interval_max_arithmetic_bits=4096,interval_max_finite_power=256,
        interval_max_exponent_bits=256,separation_factor=2,separation_margin=2,
        local_timeout_attempts_at_ceiling=2,reuse_parent_paid_responses=True,
        replay_all_existing_scores_before_provider_access=True,new_search_or_reflection_calls=False,
        test_memberships_and_final_prompts='frozen_parent',network_and_temporary_resource_retries='unchanged_indefinite')
    if policy!=expected or any(type(policy[k]) is not type(v) for k,v in expected.items()):
        raise ProtocolViolation('SCORING_CONTINUATION_POLICY_MISMATCH')


def recovery_config(config,policy):
    validate_policy(policy)
    return {**config,'local_timeout_attempts_at_ceiling':policy['local_timeout_attempts_at_ceiling']}


@lru_cache(maxsize=8192)
def _score(reference,answer,policy_json):
    policy=json.loads(policy_json)
    try:
        result=subprocess.run([sys.executable,'-m','independent_gepa.single_prompt_math.scoring_worker_v5'],
            input=json.dumps({'reference':reference,'prediction':answer,'policy':policy}),capture_output=True,
            text=True,timeout=current_worker_deadline(),env=worker_environment())
    except subprocess.TimeoutExpired as exc:raise ProtocolViolation('MATH_EVALUATOR_TIMEOUT') from exc
    except OSError as exc:
        raise ProtocolViolation('MATH_EVALUATOR_RESOURCE_TEMPORARY' if temporary_worker_resource_error(exc) else 'MATH_EVALUATOR_FAILURE') from exc
    if temporary_worker_exit(result.returncode):raise ProtocolViolation('MATH_EVALUATOR_RESOURCE_TEMPORARY')
    try:value=json.loads(result.stdout)
    except ValueError as exc:raise ProtocolViolation('MATH_EVALUATOR_RESPONSE_INVALID') from exc
    if (result.returncode or value.get('policy_sha256')!=digest(policy)
        or type(value.get('correct')) is not bool or value.get('reference_valid') is not True):
        raise ProtocolViolation('MATH_EVALUATOR_RESPONSE_INVALID')
    return value['correct']


def score(prediction,reference,*,policy):
    validate_policy(policy)
    if not isinstance(reference,str) or not reference.strip():raise ProtocolViolation('REFERENCE_UNSCORABLE')
    # Reference validation remains active even for an invalid prediction.
    return _score(reference,prediction.answer if prediction.prediction_valid else None,
                  json.dumps(policy,sort_keys=True,separators=(',',':')))
