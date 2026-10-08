"""Recheck preserved interrupted evidence without modifying original run files."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
from collections import Counter

from _bootstrap import ROOT
from independent_gepa.audit import audit_public_paths
from independent_gepa.math_comparison.benchmark import correct, team_vote, compatibility
from independent_gepa.math_comparison.contract import read, write, digest, file_hash, git
from independent_gepa.math_comparison.runtime import Runtime


def audit(run: Path, bundle: Path) -> dict:
    inventory=read(run/'owner_stop/raw_inventory.json')
    if any(file_hash(run/name)!=sha for name,sha in inventory.items()):
        raise RuntimeError('ORIGINAL_RAW_EVIDENCE_CHANGED')
    frozen=read(run/'frozen_attempt.json')
    identity=dict(frozen);expected=identity.pop('identity')
    if digest(identity)!=expected: raise RuntimeError('FROZEN_ATTEMPT_HASH_MISMATCH')
    import subprocess
    for name,sha in frozen['source_inventory'].items():
        raw=subprocess.check_output(['git','show',f'{frozen["source_sha"]}:{name}'],cwd=ROOT)
        import hashlib
        if hashlib.sha256(raw).hexdigest()!=sha: raise RuntimeError('HISTORICAL_SOURCE_FREEZE_MISMATCH')
    seal=read(run/'owner_stop/closure.json'); charge=read(run/'owner_stop/charge.json')
    charge_value=dict(charge);charge_sha=charge_value.pop('event_sha256')
    if digest(charge_value)!=charge_sha: raise RuntimeError('OWNER_CLOSURE_HASH_MISMATCH')
    journal=run/'accounting.jsonl'
    if not journal.read_bytes().endswith(b'\n'): raise RuntimeError('PARTIAL_JOURNAL_LINE')
    if file_hash(journal)!=seal['original_journal_sha256']: raise RuntimeError('ORIGINAL_JOURNAL_CHANGED')
    examples=read(bundle/'optimize.json');shell=read(bundle/'shell.json')
    closed=read(run/'SEARCH_COMPLETE.json');selections=closed['selections']
    if digest(selections)!=closed['selection_hash']: raise RuntimeError('SEARCH_SELECTION_HASH_MISMATCH')
    prototype=Runtime.__new__(Runtime);prototype.models=read(bundle/'model_contract.json')
    allowed={}
    for selection in selections:
        window=selection['window']
        proposals=read(run/f'window_{window}/proposals.json')
        prompts={'search':{'Solve the problem.',*(p['prompt'] for p in proposals)},
                 'baseline':{'Solve the problem.'},'audit':{r['prompt'] for r in selection['selected']}}
        for phase,texts in prompts.items():
            allowed[(window,phase)]={digest(prototype.request('solver',[
                {'role':'system','content':shell['system']},
                {'role':'user','content':prompt+'\n\n'+row['problem']+shell['suffix']}]))
                for prompt in texts for row in examples}
    previous='0'*64;pending={};settled=0;successes=0;roles=Counter();phases=Counter();usage={}
    cache_hits=0
    for event in (json.loads(line) for line in journal.read_bytes().splitlines()):
        value=dict(event);sha=value.pop('event_sha256')
        if value['previous_event_sha256']!=previous or digest(value)!=sha:
            raise RuntimeError('JOURNAL_CHAIN_MISMATCH')
        previous=sha
        if value['kind']=='RESERVE':
            number=value['physical_attempt'];receipt=read(run/'requests'/f'{number:06d}.json')
            request=receipt['request']
            if digest(request)!=value['request_sha256']: raise RuntimeError('REQUEST_RECEIPT_MISMATCH')
            if value['phase'] not in {'search','baseline','audit'}: raise RuntimeError('HELDOUT_ACCESS')
            if value['role']=='solver' and value['request_sha256'] not in allowed[(value['window'],value['phase'])]:
                raise RuntimeError('SOLVER_BOUNDARY_OR_OPTIMIZE_MEMBERSHIP_MISMATCH')
            pending[number]=value;roles[value['role']]+=1;phases[value['phase']]+=1
        elif value['kind'] in {'RESPONSE_CHARGE','FAILURE_CHARGE'}:
            reservation=pending.pop(value['physical_attempt']);settled+=value['amount']
            if not 0<=value['amount']<=reservation['amount']: raise RuntimeError('CHARGE_OUTSIDE_RESERVATION')
            if value['kind']=='RESPONSE_CHARGE':
                receipt=read(run/'responses'/f'{value["physical_attempt"]:06d}.json');response=receipt['response']
                if digest(response)!=value['response_sha256']: raise RuntimeError('RESPONSE_RECEIPT_MISMATCH')
                if not value['usage_reliable'] or response['input_tokens']+response['output_tokens']!=value['amount']:
                    raise RuntimeError('USAGE_RECONCILIATION_MISMATCH')
                successes+=1
                role=usage.setdefault(value['role'],{'input_tokens':0,'output_tokens':0,'settled_tokens':0})
                role['input_tokens']+=response['input_tokens'];role['output_tokens']+=response['output_tokens'];role['settled_tokens']+=value['amount']
        elif value['kind']=='CACHE_HIT': cache_hits+=1
    conservative=sum(r['amount'] for r in pending.values())
    if (previous!=seal['original_last_event_sha256'] or settled+conservative!=seal['charged_tokens']
        or conservative!=charge['charge'] or settled+conservative!=charge['closed_total']
        or len(pending)!=seal['interrupted_unresolved_physical_attempts']):
        raise RuntimeError('OWNER_CONSERVATIVE_CLOSURE_MISMATCH')
    initial=read(bundle/'audit_only/initial.json');rows=read(run/'full_metrics_progress.json')
    baseline=read(run/'window_0/baseline_full.json')
    fresh=[correct(p,e['reference']) for p,e in zip(baseline,examples,strict=True)]
    audits=[]
    for row in rows:
        predictions=read(run/f'window_{row["window"]}/full_{row["prompt_hash"]}.json')
        child=[correct(p,e['reference']) for p,e in zip(predictions,examples,strict=True)]
        old=[p[row['member']] for p in initial['correctness']];vote=oracle=0
        for index,example in enumerate(examples):
            team=[m[index] for m in initial['profiles']];team[row['member']]=predictions[index]
            vote+=team_vote(team,example['reference']);oracle+=any(correct(p,example['reference']) for p in team)
        measured=compatibility(old,child,sum(initial['vote']),vote)
        if any(row[key]!=value for key,value in measured.items()) or oracle!=row['oracle_after'] or vote!=row['team_vote_after']:
            raise RuntimeError('FULL_METRICS_REPLAY_MISMATCH')
        audits.append({'candidate_id':row['candidate_id'],'full_score':sum(child),'vote':vote,'oracle':oracle,
                      'scoring_retention_vote_oracle_v22':'PASS'})
    solver_logical=0;guard_scores=0
    for window in range(7):
        for value in (json.loads(line) for line in (run/f'window_{window}/evaluations.jsonl').read_bytes().splitlines()):
            if value['contract_valid']: solver_logical+=len(value['ids'])
            else: guard_scores+=len(value['ids'])
    return {'status':'PASS_FOR_PRESERVED_PREFIX_AND_CONSERVATIVE_OWNER_CLOSURE',
        'whole_comparison_integrity':'INVALID','whole_comparison_complete':False,
        'original_source_sha':frozen['source_sha'],'attempt_identity':expected,'provider_calls_by_this_audit':0,
        'original_source_freeze':'PASS','original_raw_preservation':'PASS','journal_chain_and_receipts':'PASS',
        'solver_immutable_boundary_and_optimize_membership':'PASS',
        'source_copy_conformance':'FAIL_AS_RECORDED_BY_OWNER_STOP',
        'known_settled_tokens':settled,'conservative_unknown_request_charge':conservative,
        'charged_tokens':settled+conservative,'physical_attempts':sum(roles.values()),'complete_response_receipts':successes,
        'physical_attempts_by_role':dict(roles),'physical_attempts_by_phase':dict(phases),'settled_usage_by_role':usage,
        'solver_cache_hits':cache_hits,'native_search_metric_scores':solver_logical+guard_scores,
        'actual_search_solver_logical_evaluations':solver_logical,'guard_rejection_metric_scores':guard_scores,
        'fresh_initial_correct':sum(fresh),'fresh_initial_correctness_equals_historical':fresh==[r[0] for r in initial['correctness']],
        'completed_full_candidates':audits,'unknown_full_candidates':sum(len(s['selected']) for s in selections)-len(audits),
        'shadow_calls':0,'validation_calls':0,'test_calls':0,'team_commits':0,
        'invoice_cost':'NOT_AVAILABLE','original_runner_terminal_receipt_present':(run/'completion.json').exists()}


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-run',type=Path,required=True);parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    for name in list(os.environ):
        if 'API_KEY' in name or 'BASE_URL' in name: os.environ.pop(name,None)
    def blocked(*args,**kwargs): raise RuntimeError('OFFLINE_NETWORK_FORBIDDEN')
    socket.socket.connect=socket.socket.connect_ex=socket.create_connection=socket.getaddrinfo=blocked
    value=audit(args.private_run.resolve(),args.bundle.resolve());write(args.output,value)
    if audit_public_paths([args.output]): raise RuntimeError('PUBLIC_AUDIT_SANITIZATION_FAILED')
    print(f'PASS preserved-prefix audit: completed_full={len(value["completed_full_candidates"])} charged={value["charged_tokens"]}')


if __name__=='__main__': main()
