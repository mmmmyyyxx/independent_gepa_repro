"""Draft receipt, recovery, scoring, split and accounting replay.

Not yet validated against a complete independent-review execution; readiness
remains HOLD in the V4 engineering stop record.
"""
from __future__ import annotations
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from ..protocol import ProtocolViolation
from .benchmark import classify,correct,compatibility,team_vote
from .contract import read,digest,file_hash,validate_bundle
from .runtime import Runtime,audit_accounting
from .conformance import verify_final_release


def audit_complete(root: Path,run: Path,bundle: Path) -> dict[str,Any]:
    frozen=read(run/'frozen_attempt.json');identity=frozen['identity'];check=dict(frozen);check.pop('identity')
    if digest(check)!=identity or validate_bundle(bundle)['bundle_hash']!=frozen['bundle_hash']:
        raise ProtocolViolation('AUDIT_FROZEN_IDENTITY_MISMATCH')
    fake=frozen.get('fake_only_engineering_fixture') is True
    for name,sha in frozen['source_inventory'].items():
        raw=(root/name).read_bytes() if fake else subprocess.check_output(['git','show',f'{frozen["source_sha"]}:{name}'],cwd=root)
        if hashlib.sha256(raw).hexdigest()!=sha:raise ProtocolViolation('AUDIT_SOURCE_FREEZE_MISMATCH')
    closed=read(run/'SEARCH_COMPLETE.json');pool=closed['selections'];cfg=frozen['config']
    if len(pool)!=7 or digest(pool)!=closed['selection_hash']:raise ProtocolViolation('AUDIT_SELECTION_FREEZE_MISMATCH')
    verify_final_release(run,identity,pool,cfg['reviewer_identity'])
    terminal=read(run/'completion.json')
    if terminal['status']!='EXECUTION_COMPLETE':raise ProtocolViolation('AUDIT_EXECUTION_NOT_COMPLETE')
    accounting=audit_accounting(run);examples=read(bundle/'optimize.json');shell=read(bundle/'shell.json')
    models=read(bundle/'model_contract.json');prototype=Runtime.__new__(Runtime);prototype.models=models
    allowed={};keys={}
    for s in pool:
        prompts={p['prompt_hash']:p['prompt'] for p in read(run/f'window_{s["window"]}/proposals.json') if p['contract_valid']}
        initial=hashlib.sha256(b'Solve the problem.').hexdigest();prompts[initial]='Solve the problem.'
        selected=set(s['selected_hashes']);w=s['window'];m=s['member']
        for ph,prompt in prompts.items():
            for e in examples:
                request=prototype.request('solver',[{'role':'system','content':shell['system']},
                    {'role':'user','content':prompt+'\n\n'+e['problem']+shell['suffix']}])
                key=digest({'attempt':identity,'window':w,'member':m,'request':request})
                row=(key,e,ph);allowed[(w,digest(request))]=row;keys[(w,key)]=row
    pending={};resolved={};draws={};roles=Counter();phases=Counter();usage=Counter();hits=0;approved=set()
    for event in map(json.loads,(run/'accounting.jsonl').read_bytes().splitlines()):
        kind=event['kind']
        if kind=='CANDIDATE_REVIEW_DECISION':
            if event['status']=='PASS':approved.add((event['window'],event['prompt_hash']))
        elif kind=='RESERVE':
            receipt=read(run/'requests'/f'{event["physical_attempt"]:06d}.json');request=receipt['request']
            if digest(request)!=event['request_sha256']:raise ProtocolViolation('AUDIT_WIRE_RECEIPT_MISMATCH')
            if event['phase'] not in {'search','baseline','audit'}:raise ProtocolViolation('AUDIT_HELDOUT_ACCESS')
            if event['role']=='solver':
                row=allowed.get((event['window'],event['request_sha256']))
                if row is None:raise ProtocolViolation('AUDIT_SOLVER_BOUNDARY_OR_MEMBERSHIP_MISMATCH')
                key,e,ph=row
                if ph!=initial and (event['window'],ph) not in approved:raise ProtocolViolation('AUDIT_SOLVER_BEFORE_APPROVAL')
                if (event['phase']=='baseline' and ph!=initial
                    or event['phase']=='audit' and ph not in pool[event['window']]['selected_hashes']):
                    raise ProtocolViolation('AUDIT_PHASE_PROMPT_MISMATCH')
                if key in resolved:raise ProtocolViolation('AUDIT_REPEATED_PROVIDER_REALIZATION_AFTER_RESOLUTION')
            elif event['role']=='reflection':
                if event['phase']!='search' or request!=prototype.request('reflection',request['messages']):
                    raise ProtocolViolation('AUDIT_REFLECTION_DECODING_MISMATCH')
                row=None
            else:raise ProtocolViolation('AUDIT_UNKNOWN_ROLE')
            pending[event['physical_attempt']]=(event,row);roles[event['role']]+=1;phases[event['phase']]+=1
        elif kind in {'RESPONSE_CHARGE','FAILURE_CHARGE'}:
            reservation,row=pending.pop(event['physical_attempt'])
            if not 0<=event['amount']<=reservation['amount']:raise ProtocolViolation('AUDIT_CHARGE_OUTSIDE_RESERVATION')
            usage[event['role']]+=event['amount']
            if kind=='FAILURE_CHARGE':continue
            receipt=read(run/'responses'/f'{event["physical_attempt"]:06d}.json');response=receipt['response']
            if (digest(response)!=event['response_sha256'] or not event['usage_reliable']
                or response['input_tokens']+response['output_tokens']!=event['amount']
                or response.get('reasoning_character_count',0) or (response.get('reasoning_tokens') or 0)>0):
                raise ProtocolViolation('AUDIT_RESPONSE_USAGE_OR_THINKING_MISMATCH')
            if row is not None:
                key,e,ph=row;prediction=classify(response.get('text'),response.get('finish_reason'))
                batch=draws.setdefault(key,[]);batch.append(prediction)
                if len(batch)>4:raise ProtocolViolation('AUDIT_SEMANTIC_DRAW_CAP_EXCEEDED')
                if prediction['prediction_valid'] or len(batch)==4:
                    result={**prediction,'semantic_attempt_count':len(batch),'raw_invalid_count':sum(not p['prediction_valid'] for p in batch),
                        'terminal_invalid':not prediction['prediction_valid'],'original_predictions':batch,
                        'correct':correct(prediction,e['reference']),
                        'immutable_single_line_obeyed':bool(isinstance(prediction['text'],str) and re.fullmatch(r'FINAL_ANSWER:[^\r\n]+',prediction['text'].strip()))}
                    if read(run/'cache'/f'{key}.json')!=result:raise ProtocolViolation('AUDIT_RESOLVED_CACHE_REPLAY_MISMATCH')
                    resolved[key]=result
        elif kind=='CACHE_HIT':
            row=keys.get((event['window'],event['key']))
            if row is None or row[0] not in resolved:raise ProtocolViolation('AUDIT_CACHE_REALIZATION_OR_MEMBERSHIP_MISMATCH')
            hits+=1
    if pending:raise ProtocolViolation('AUDIT_PENDING_REQUESTS')
    initial_profiles=read(bundle/'audit_only/initial.json');rows=read(run/'candidate_metrics.json');baseline_stats=read(run/'realization_diagnostics.json')
    planned={(s['window'],p['prompt_hash']) for s in pool for p in s['selected']}
    if {(r['window'],r['prompt_hash']) for r in rows}!=planned or len(rows)!=len(planned):
        raise ProtocolViolation('AUDIT_FULL_POOL_INCOMPLETE')
    for s,b in zip(pool,baseline_stats,strict=True):
        baseline=read(run/f'window_{s["window"]}/baseline_full.json')
        if len(baseline)!=60 or sum(correct(p,e['reference']) for p,e in zip(baseline,examples,strict=True))!=b['fresh_initial_correct']:
            raise ProtocolViolation('AUDIT_BASELINE_SCORE_MISMATCH')
    for row in rows:
        predictions=read(run/f'window_{row["window"]}/full_{row["prompt_hash"]}.json')
        if len(predictions)!=60:raise ProtocolViolation('AUDIT_FULL60_SHAPE')
        child=[correct(p,e['reference']) for p,e in zip(predictions,examples,strict=True)]
        old=[r[row['member']] for r in initial_profiles['correctness']];vote=oracle=0
        for i,e in enumerate(examples):
            team=[p[i] for p in initial_profiles['profiles']];team[row['member']]=predictions[i]
            vote+=team_vote(team,e['reference']);oracle+=any(correct(p,e['reference']) for p in team)
        measured=compatibility(old,child,sum(initial_profiles['vote']),vote)
        if any(row[k]!=v for k,v in measured.items()) or vote!=row['team_vote_after'] or oracle!=row['oracle_after']:
            raise ProtocolViolation('AUDIT_FULL_RETENTION_VOTE_ORACLE_MISMATCH')
        baseline=read(run/f'window_{row["window"]}/baseline_full.json')
        fresh=compatibility([correct(p,e['reference']) for p,e in zip(baseline,examples,strict=True)],child,sum(initial_profiles['vote']),vote)
        if row['fresh_parent_delta']!=fresh['net_competence_gain'] or row['fresh_parent_lost']!=fresh['original_correct_lost']:
            raise ProtocolViolation('AUDIT_FRESH_PARENT_MISMATCH')
    logical=sum(s['actual_solver_logical_evaluations'] for s in pool)
    expected_logical={'search':logical,'baseline':420,'audit':60*len(rows)}
    if (terminal['accounting']['logical_evaluations']!=expected_logical or accounting['charged_tokens']>cfg['token_ceiling']
        or accounting['physical_attempts']>cfg['physical_attempt_ceiling'] or hits!=terminal['accounting']['cache_hits']):
        raise ProtocolViolation('AUDIT_LOGICAL_OR_RESOURCE_TOTAL_MISMATCH')
    return {'identity':'MATH_GEPA_COMPLETE_OWNER_AUDIT_V1','status':'PASS',
        'scientific_status':'FAKE_ENGINEERING_FIXTURE' if fake else 'VALID','attempt_identity':identity,
        'source_sha':frozen['source_sha'],'provider_calls_by_audit':0,'frozen_source_and_bundle':'PASS',
        'pre_solver_and_final_review':'PASS','wire_membership_decoding_recovery_cache':'PASS',
        'full_scoring_retention_fresh_parent_vote_oracle':'PASS','accounting_and_resource_ceiling':'PASS',
        'generated':sum(s['proposal_count'] for s in pool),'full_candidates':len(rows),
        'charged_tokens':accounting['charged_tokens'],'physical_attempts':accounting['physical_attempts'],
        'role_charged_tokens':dict(usage),'physical_by_role':dict(roles),'physical_by_phase':dict(phases),
        'cache_hits':hits,'logical_evaluations':expected_logical,'reserved_inflight':0,
        'shadow_calls':0,'validation_calls':0,'test_calls':0,'team_commits':0,
        'authorization_closed':True,'automatic_retry_authorized':False}
