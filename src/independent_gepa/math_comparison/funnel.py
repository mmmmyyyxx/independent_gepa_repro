"""Complete generated and measured candidate accounting, without best-only reporting."""
from __future__ import annotations

from collections import Counter
from typing import Any

from .search import INITIAL,prompt_hash
from ..protocol import ProtocolViolation


def candidate_funnel(selections: list[dict[str,Any]],rows: list[dict[str,Any]]) -> dict[str,Any]:
    measured={(r['window'],r['prompt_hash']):r for r in rows}
    planned={(s['window'],r['prompt_hash']) for s in selections for r in s['selected']}
    if len(measured)!=len(rows) or not set(measured)<=planned:
        raise ProtocolViolation('FULL_FUNNEL_MEMBERSHIP_MISMATCH')
    initial=prompt_hash(INITIAL);windows=[];candidates=[];reasons=Counter()
    for selection in selections:
        proposals=selection.get('proposal_audit',[])
        selected=set(selection['selected_hashes'])
        for row in proposals:
            measurement=measured.get((selection['window'],row['prompt_hash']))
            if measurement and not row['contract_valid']:
                raise ProtocolViolation('INVALID_PROCEDURE_HAS_FULL_MEASUREMENT')
            failures=row.get('contract_failures',[])
            if not row['contract_valid']:reasons.update(failures)
            candidates.append({'window':selection['window'],'member':selection['member'],
                'generation':row['generation'],'prompt_hash':row['prompt_hash'],
                'contract_valid':row['contract_valid'],'failure_categories':failures,
                'selected_for_full':row['prompt_hash'] in selected,'full_evaluated':measurement is not None,
                'member_improving':measurement['candidate_member_correct']>22 if measurement else None,
                'fresh_parent_improving':measurement['fresh_parent_delta']>0 if measurement else None,
                'v22_admissible':measurement['v22_admissible'] if measurement else None,
                'pure_repair':measurement['PURE_REPAIR'] if measurement else None})
        windows.append({'window':selection['window'],'member':selection['member'],
            'generated':len(proposals),'contract_valid':sum(p['contract_valid'] for p in proposals),
            'contract_invalid':sum(not p['contract_valid'] for p in proposals),
            'unique_contract_valid_changed':len({p['prompt_hash'] for p in proposals if p['contract_valid'] and p['prompt_hash']!=initial}),
            'selected_for_full':len(selected),'full_evaluated':sum((selection['window'],h) in measured for h in selected),
            'native_best_is_initial':selection['native_best_hash']==initial})
    return {'identity':'MATH_GEPA_ALL_GENERATED_FUNNEL_V1','counting_unit':'generated_instances; Full rows are distinct per window',
        'generated':sum(w['generated'] for w in windows),'contract_valid':sum(w['contract_valid'] for w in windows),
        'contract_invalid':sum(w['contract_invalid'] for w in windows),'selected_for_full':sum(w['selected_for_full'] for w in windows),
        'full_evaluated':len(rows),'member_improving':sum(r['candidate_member_correct']>22 for r in rows),
        'fresh_parent_improving':sum(r['fresh_parent_delta']>0 for r in rows),
        'v22_admissible':sum(r['v22_admissible'] for r in rows),'pure_repairs':sum(r['PURE_REPAIR'] for r in rows),
        'invalid_failure_categories':dict(sorted(reasons.items())),'windows':windows,'candidates':candidates,
        'unmeasured_outcomes_are_unknown':True,'guard_pass_is_not_semantic_novelty_proof':True}
