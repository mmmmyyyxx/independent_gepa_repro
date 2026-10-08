"""A4 MATH parser, recovery and equal plurality parity without sibling imports."""
from __future__ import annotations

from functools import lru_cache
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..protocol import ProtocolViolation
from .contract import SETTINGS

def worker_environment() -> dict[str,str]:
    # Subprocesses resolve only this self-contained package, never the sibling checkout.
    return {**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[2])}

@lru_cache(maxsize=4096)
def matrix(expressions: tuple[str,...]) -> dict[str,Any]:
    if not expressions or len(expressions)>6 or any(not isinstance(x,str) or len(x)>2048 for x in expressions):
        raise ProtocolViolation('MATH_EXPRESSION_SHAPE_INVALID')
    try:
        result = subprocess.run([sys.executable,'-m','independent_gepa.math_comparison.math_domain_worker'],
            input=json.dumps({'expressions':expressions}), capture_output=True, text=True,
            timeout=SETTINGS['process_deadline'],check=False,env=worker_environment())
        data = json.loads(result.stdout)
        if (result.returncode or len(data['valid'])!=len(expressions)
            or len(data['equivalence'])!=len(expressions)
            or any(len(r)!=len(expressions) for r in data['equivalence'])
            or any(type(x) is not bool for x in data['valid'])
            or any(type(x) is not bool for r in data['equivalence'] for x in r)):
            raise ProtocolViolation('MATH_EVALUATOR_FAILURE')
        return data
    except (subprocess.TimeoutExpired, OSError, ValueError,KeyError) as exc:
        raise ProtocolViolation('MATH_EVALUATOR_FAILURE') from exc

@lru_cache(maxsize=4096)
def classify_payload(expression: str) -> str|None:
    if len(expression)>2048: return 'PAYLOAD_UNSUPPORTED'
    try:
        result = subprocess.run([sys.executable,'-m','independent_gepa.math_comparison.math_prediction_worker'],
            input=json.dumps({'expression':expression}),capture_output=True,text=True,
            timeout=SETTINGS['process_deadline'],check=False,env=worker_environment())
    except subprocess.TimeoutExpired:
        return 'PAYLOAD_PARSE_FAILURE'
    except OSError as exc:
        raise ProtocolViolation('MATH_PREDICTION_WORKER_UNAVAILABLE') from exc
    try:
        data = json.loads(result.stdout)
    except ValueError as exc:
        raise ProtocolViolation('MATH_PREDICTION_WORKER_RESPONSE_INVALID') from exc
    if result.returncode or set(data)!={'invalid_reason'} or data['invalid_reason'] not in (None,'PAYLOAD_PARSE_FAILURE','PAYLOAD_UNSUPPORTED'):
        raise ProtocolViolation('MATH_PREDICTION_WORKER_FAILURE')
    return data['invalid_reason']

def classify(text: str|None, finish_reason: str|None='stop') -> dict[str,Any]:
    if text is not None and not isinstance(text,str): raise ProtocolViolation('MATH_PREDICTION_SERIALIZATION_INVALID')
    lines = [line.strip() for line in (text or '').splitlines() if line.strip()]
    markers = [line for line in lines if line.startswith('FINAL_ANSWER:')]
    answer = ''
    if finish_reason in {'length','max_tokens','max_output_tokens'}: reason = 'OUTPUT_TRUNCATED'
    elif finish_reason!='stop': reason = 'OTHER_PREDICTION_CONTRACT_FAILURE'
    elif not markers: reason = 'MISSING_FINAL_MARKER'
    elif len(markers)>1: reason = 'MULTIPLE_FINAL_MARKERS'
    elif not markers[0].removeprefix('FINAL_ANSWER:').strip(): reason = 'EMPTY_FINAL_PAYLOAD'
    elif lines[-1]!=markers[0]: reason = 'OTHER_PREDICTION_CONTRACT_FAILURE'
    else:
        answer = markers[0].removeprefix('FINAL_ANSWER:').strip()
        reason = classify_payload(answer)
    return {'text':text,'finish_reason':finish_reason,'answer':answer if reason is None else '',
            'prediction_valid':reason is None,'invalid_reason':reason}

def require_reference(reference: str) -> None:
    value = matrix((reference,))
    if not reference.strip() or not value['valid'][0] or not value['equivalence'][0][0]:
        raise ProtocolViolation('REFERENCE_UNSCORABLE')

def correct(prediction: dict[str,Any], reference: str) -> bool:
    require_reference(reference)
    if not prediction['prediction_valid']: return False
    value = matrix((reference,prediction['answer']))
    if not value['valid'][0]: raise ProtocolViolation('REFERENCE_UNSCORABLE')
    return bool(value['valid'][1] and value['equivalence'][0][1])

def team_vote(predictions: list[dict[str,Any]], reference: str) -> bool:
    if len(predictions)!=5: raise ProtocolViolation('TEAM_REQUIRES_FIVE')
    valid = [i for i,p in enumerate(predictions) if p['prediction_valid']]
    if not valid: return False
    value = matrix(tuple(predictions[i]['answer'] for i in valid)); relation = value['equivalence']
    n = len(valid)
    if (any(not relation[i][i] for i in range(n))
        or any(relation[i][j]!=relation[j][i] for i in range(n) for j in range(n))
        or any(relation[i][j] and relation[j][k] and not relation[i][k]
            for i in range(n) for j in range(n) for k in range(n))):
        return False  # A4 abstains on an inconsistent finite relation.
    groups = []; assigned: set[int] = set()
    for i in range(n):
        if i not in assigned:
            group = [j for j in range(n) if relation[i][j]]
            assigned.update(group); groups.append(group)
    groups.sort(key=lambda g:(-len(g),g[0]))
    if len(groups)>1 and len(groups[0])==len(groups[1]): return False
    return correct(predictions[valid[groups[0][0]]],reference)

def compatibility(old: list[bool], child: list[bool], vote_before: int, vote_after: int) -> dict[str,Any]:
    if len(old)!=60 or len(child)!=60: raise ProtocolViolation('FULL60_SUPPORT_REQUIRED')
    retained = sum(a and b for a,b in zip(old,child,strict=True))
    lost = sum(a and not b for a,b in zip(old,child,strict=True))
    new = sum(not a and b for a,b in zip(old,child,strict=True))
    floor = sum(child)>=sum(old); progress = sum(child)>sum(old) or vote_after>vote_before
    return {'initial_member_correct':sum(old),'candidate_member_correct':sum(child),
        'original_correct_retained':retained,'original_correct_lost':lost,'newly_correct':new,
        'net_competence_gain':new-lost,'member_accuracy_delta':(new-lost)/60,
        'PURE_REPAIR':new>0 and lost==0,'NET_POSITIVE':new>lost,
        'ADMISSIBLE_TARGET_GAIN':sum(child)>sum(old), 'competence_floor_satisfied':floor,
        'target_progress_satisfied':sum(child)>sum(old),
        'v22_admissible':floor and vote_after>=vote_before and progress}
