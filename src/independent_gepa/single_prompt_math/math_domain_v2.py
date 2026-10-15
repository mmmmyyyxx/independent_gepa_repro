"""Unchanged pinned mathematical physics with a phase-scoped worker deadline."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
import json
import subprocess
import sys

from ..protocol import ProtocolViolation as SearchContractError
from ..math_comparison.contract import SETTINGS
from ..math_comparison.benchmark import worker_environment
from .recovery import temporary_worker_resource_error,temporary_worker_exit

_DEADLINE=ContextVar('single_prompt_math_worker_deadline',default=8)


def current_worker_deadline():return _DEADLINE.get()


@contextmanager
def worker_deadline(seconds):
    if type(seconds) is not int or seconds<8:raise SearchContractError('MATH_WORKER_DEADLINE_INVALID')
    token=_DEADLINE.set(seconds)
    try:yield
    finally:_DEADLINE.reset(token)


@lru_cache(maxsize=4096)
def domain_matrix(expressions):
    if not expressions or len(expressions)>6 or any(not isinstance(x,str) or len(x)>2048 for x in expressions):
        raise SearchContractError('MATH_EXPRESSION_SHAPE_INVALID')
    try:
        result=subprocess.run([sys.executable,'-m','independent_gepa.math_comparison.math_domain_worker'],
            input=json.dumps({'expressions':expressions}),capture_output=True,text=True,
            timeout=_DEADLINE.get(),check=False,env=worker_environment())
        if temporary_worker_exit(result.returncode):raise SearchContractError('MATH_EVALUATOR_RESOURCE_TEMPORARY')
        if result.returncode:raise SearchContractError('MATH_EVALUATOR_FAILURE')
        data=json.loads(result.stdout)
        if (len(data['valid'])!=len(expressions) or len(data['equivalence'])!=len(expressions)
            or any(len(row)!=len(expressions) for row in data['equivalence'])
            or any(type(v) is not bool for v in data['valid'])
            or any(type(v) is not bool for row in data['equivalence'] for v in row)):
            raise SearchContractError('MATH_EVALUATOR_RESPONSE_INVALID')
        return data
    except subprocess.TimeoutExpired as exc:raise SearchContractError('MATH_EVALUATOR_TIMEOUT') from exc
    except OSError as exc:
        category='MATH_EVALUATOR_RESOURCE_TEMPORARY' if temporary_worker_resource_error(exc) else 'MATH_EVALUATOR_FAILURE'
        raise SearchContractError(category) from exc
    except (ValueError,KeyError) as exc:raise SearchContractError('MATH_EVALUATOR_FAILURE') from exc


def require_scorable(reference):
    if not isinstance(reference,str) or not reference.strip():raise SearchContractError('REFERENCE_UNSCORABLE')
    value=domain_matrix((reference,))
    if not value['valid'][0] or not value['equivalence'][0][0]:raise SearchContractError('REFERENCE_UNSCORABLE')


def score(prediction,reference):
    require_scorable(reference)
    if not prediction.prediction_valid:return False
    value=domain_matrix((reference,prediction.answer))
    if not value['valid'][0]:raise SearchContractError('REFERENCE_UNSCORABLE')
    return bool(value['valid'][1] and value['equivalence'][0][1])
