"""The pinned payload parser, with infrastructure timeouts kept out of model errors."""
from functools import lru_cache
import json
import subprocess
import sys

from ..protocol import ProtocolViolation
from ..math_comparison.benchmark import worker_environment
from .math_domain_v2 import current_worker_deadline
from .recovery import temporary_worker_resource_error,temporary_worker_exit


@lru_cache(maxsize=4096)
def classify_payload(expression):
    if len(expression)>2048:return 'PAYLOAD_UNSUPPORTED'
    try:
        result=subprocess.run([sys.executable,'-m','independent_gepa.math_comparison.math_prediction_worker'],
            input=json.dumps({'expression':expression}),capture_output=True,text=True,
            timeout=current_worker_deadline(),check=False,env=worker_environment())
    except subprocess.TimeoutExpired as exc:raise ProtocolViolation('MATH_EVALUATOR_TIMEOUT') from exc
    except OSError as exc:
        category='MATH_EVALUATOR_RESOURCE_TEMPORARY' if temporary_worker_resource_error(exc) else 'MATH_PREDICTION_WORKER_UNAVAILABLE'
        raise ProtocolViolation(category) from exc
    if temporary_worker_exit(result.returncode):raise ProtocolViolation('MATH_EVALUATOR_RESOURCE_TEMPORARY')
    try:data=json.loads(result.stdout)
    except ValueError as exc:raise ProtocolViolation('MATH_PREDICTION_WORKER_RESPONSE_INVALID') from exc
    if (result.returncode or not isinstance(data,dict) or set(data)!={'invalid_reason'}
        or data['invalid_reason'] not in (None,'PAYLOAD_PARSE_FAILURE','PAYLOAD_UNSUPPORTED')):
        raise ProtocolViolation('MATH_PREDICTION_WORKER_FAILURE')
    return data['invalid_reason']
