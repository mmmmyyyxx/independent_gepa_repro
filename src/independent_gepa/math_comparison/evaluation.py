"""Post-selection Full60 audits never update GEPA or choose another search."""
from __future__ import annotations

from pathlib import Path
import hashlib
from typing import Any

from ..protocol import ProtocolViolation
from .benchmark import compatibility,correct,matrix,team_vote
from .contract import read,write
from .runtime import Runtime
from .search import INITIAL
from .candidate_guard import candidate_valid

def behavior_changes(old: list[dict[str,Any]],child: list[dict[str,Any]]) -> int:
    changed=0
    for a,b in zip(old,child,strict=True):
        if a['prediction_valid']!=b['prediction_valid']:
            changed+=1
        elif a['prediction_valid']:
            value=matrix((a['answer'],b['answer']))
            if value['equivalence'][0][1]!=value['equivalence'][1][0]:
                raise ProtocolViolation('BEHAVIOR_EQUIVALENCE_ASYMMETRIC')
            changed+=not value['equivalence'][0][1]
    return changed

def audit_selected(runtime: Runtime,bundle: Path,examples: list[dict[str,Any]],selections: list[dict[str,Any]],
                   private: Path) -> tuple[list[dict[str,Any]],list[dict[str,Any]]]:
    if not (private/'SEARCH_COMPLETE.json').exists(): raise ProtocolViolation('SEARCH_FREEZE_REQUIRED_BEFORE_AUDIT')
    # Check the complete frozen pool before any paid baseline or audit request.
    if any(not candidate_valid(row['prompt'],examples) for selection in selections for row in selection['selected']):
        raise ProtocolViolation('FROZEN_CANDIDATE_CONFORMANCE_FAILURE')
    original=read(bundle/'audit_only/initial.json')
    profiles=original['profiles']; old_correct=original['correctness']; vote_before=sum(original['vote'])
    if len(profiles)!=5 or any(len(p)!=60 for p in profiles): raise ProtocolViolation('FIXED_PEER_SHAPE_MISMATCH')
    original_scores=[sum(row[member] for row in old_correct) for member in range(5)]
    if original_scores!=[22]*5 or vote_before!=22: raise ProtocolViolation('ORIGINAL_A4_BASELINE_MISMATCH')
    # Independently rescore every frozen historical profile before using the diagnostic.
    for index,example in enumerate(examples):
        for member in range(5):
            if correct(profiles[member][index],example['reference'])!=old_correct[index][member]:
                raise ProtocolViolation('HISTORICAL_BASELINE_SCORER_PARITY_FAILURE')
        if team_vote([p[index] for p in profiles],example['reference'])!=original['vote'][index]:
            raise ProtocolViolation('HISTORICAL_BASELINE_VOTE_PARITY_FAILURE')
    rows=[]; baselines=[]
    for selection in selections:
        window=selection['window']; member=selection['member']
        baseline=[runtime.solve(INITIAL,example,window,member,'baseline') for example in examples]
        baseline_vector=[p['correct'] for p in baseline]
        old_vector=[row[member] for row in old_correct]
        baselines.append({'window':window,'member':member,'fresh_initial_correct':sum(baseline_vector),
            'historical_initial_correct':22,'correctness_disagreement':sum(a!=b for a,b in zip(old_vector,baseline_vector,strict=True)),
            'behavior_changes':behavior_changes(profiles[member],baseline),
            'invalid_count':sum(not p['prediction_valid'] for p in baseline)})
        write(private/f'window_{window}/baseline_full.json',baseline)
        for selected in selection['selected']:
            candidate=[runtime.solve(selected['prompt'],example,window,member,'audit') for example in examples]
            scores=[p['correct'] for p in candidate]; vote_after=0; oracle_after=0
            for index,example in enumerate(examples):
                team=[p[index] for p in profiles]; team[member]=candidate[index]
                vote_after+=team_vote(team,example['reference'])
                oracle_after+=any(correct(p,example['reference']) for p in team)
            metrics=compatibility(old_vector,scores,vote_before,vote_after)
            fresh=compatibility(baseline_vector,scores,vote_before,vote_after)
            row={**{k:v for k,v in selected.items() if k!='prompt'},'candidate_id':f'w{window}-{selected["prompt_hash"][:12]}',
                'window':window,'member':member,**metrics,'fresh_parent_member_correct':sum(baseline_vector),
                'fresh_parent_retained':fresh['original_correct_retained'],
                'fresh_parent_lost':fresh['original_correct_lost'],'fresh_parent_new':fresh['newly_correct'],
                'fresh_parent_delta':fresh['net_competence_gain'],
                'team_vote_before':vote_before,'team_vote_after':vote_after,'team_vote_delta':vote_after-vote_before,
                'oracle_before':22,'oracle_after':oracle_after,'oracle_delta':oracle_after-22,
                'novel_correct_coverage':sum(not any(old_correct[i]) and scores[i] for i in range(60)),
                'new_correct_on_historical_terminal_invalid':sum(not profiles[member][i]['prediction_valid'] and scores[i] for i in range(60)),
                'vote_conversion':vote_after-vote_before,
                'behavior_change_count':behavior_changes(profiles[member],candidate),
                'fresh_parent_behavior_change_count':behavior_changes(baseline,candidate),
                'candidate_invalid_output_count':sum(not p['prediction_valid'] for p in candidate),
                'raw_invalid_count':sum(p['raw_invalid_count'] for p in candidate),
                'candidate_correctness_vector_sha256':hashlib.sha256(bytes(scores)).hexdigest(),
                'mutation_category':'reusable_reasoning_edit_bounded_contract_valid',
                'safety_guard':'prediction_validity_v2_invalidity_through_incorrectness',
                'shadow_measured':False,'deployment_authorized':False,'TeamProbe_promotion':'NOT_MEASURED'}
            rows.append(row)
            write(private/f'window_{window}/full_{selected["prompt_hash"]}.json',candidate)
            write(private/'full_metrics_progress.json',rows)
            print(f'Full60 window={window} member={member} correct={sum(scores)} retained={metrics["original_correct_retained"]} '
                  f'lost={metrics["original_correct_lost"]} new={metrics["newly_correct"]} admissible={metrics["v22_admissible"]}',flush=True)
    return rows,baselines
