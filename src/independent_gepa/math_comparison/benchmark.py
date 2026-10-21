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

def classify_payload(expression):
    # Prediction validity is extraction-only, never a symbolic parser decision.
    return None if isinstance(expression, str) else 'extraction_failure'

def classify(text, finish_reason='stop'):
    from dataclasses import asdict
    from ..single_prompt_math.math_flexible_answer import classify_prediction
    return asdict(classify_prediction(text, finish_reason))

def require_reference(reference):
    from ..math_scoring import prepare_ground_truth
    prepare_ground_truth(reference)

def correct(prediction, reference):
    from ..math_scoring import score_math_response
    return score_math_response(prediction.get('text'), reference).correct

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
