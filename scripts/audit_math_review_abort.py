"""Offline audit of a completed search stopped by the pre-Full owner barrier."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess

from _bootstrap import ROOT
from independent_gepa.audit import audit_public_paths
from independent_gepa.math_comparison.contract import digest, file_hash, read, write, validate_bundle
from independent_gepa.math_comparison.runtime import Runtime, audit_accounting


def audit(run: Path, bundle: Path, seal_path: Path) -> dict:
    seal=read(seal_path)
    actual={str(p.relative_to(run)).replace('\\','/'):file_hash(p) for p in sorted(run.rglob('*')) if p.is_file()}
    if actual!=seal['files'] or digest(actual)!=seal['inventory_sha256']:
        raise RuntimeError('ORIGINAL_EVIDENCE_CHANGED')
    frozen=read(run/'frozen_attempt.json');check=dict(frozen);identity=check.pop('identity')
    if digest(check)!=identity or validate_bundle(bundle)['bundle_hash']!=frozen['bundle_hash']:
        raise RuntimeError('FROZEN_ATTEMPT_OR_BUNDLE_MISMATCH')
    for name,sha in frozen['source_inventory'].items():
        raw=subprocess.check_output(['git','show',f'{frozen["source_sha"]}:{name}'],cwd=ROOT)
        if hashlib.sha256(raw).hexdigest()!=sha: raise RuntimeError('SOURCE_FREEZE_MISMATCH')
    closed=read(run/'SEARCH_COMPLETE.json');selections=closed['selections']
    review=read(run/'owner_conformance.json');rc=dict(review);rsha=rc.pop('receipt_sha256')
    if (digest(selections)!=closed['selection_hash'] or digest(rc)!=rsha
        or review['attempt_identity']!=identity or review['selection_hash']!=closed['selection_hash']
        or review['status']!='FAIL' or review['full_outcomes_read'] is not False):
        raise RuntimeError('OWNER_REVIEW_OR_SEARCH_FREEZE_MISMATCH')
    examples=read(bundle/'optimize.json');shell=read(bundle/'shell.json')
    prototype=Runtime.__new__(Runtime);prototype.models=read(bundle/'model_contract.json')
    allowed={}
    for s in selections:
        prompts={'Solve the problem.',*(p['prompt'] for p in read(run/f'window_{s["window"]}/proposals.json'))}
        allowed[s['window']]={digest(prototype.request('solver',[
            {'role':'system','content':shell['system']},
            {'role':'user','content':p+'\n\n'+e['problem']+shell['suffix']}])) for p in prompts for e in examples}
    roles=Counter();phases=Counter();settled=Counter();pending={};previous='0'*64;cache_hits=0
    for event in map(json.loads,(run/'accounting.jsonl').read_bytes().splitlines()):
        value=dict(event);sha=value.pop('event_sha256')
        if value['previous_event_sha256']!=previous or digest(value)!=sha: raise RuntimeError('JOURNAL_CHAIN_MISMATCH')
        previous=sha
        if value['kind']=='RESERVE':
            number=value['physical_attempt'];receipt=read(run/'requests'/f'{number:06d}.json')
            if number in pending or digest(receipt['request'])!=value['request_sha256']:
                raise RuntimeError('REQUEST_RECEIPT_MISMATCH')
            if value['phase']!='search': raise RuntimeError('NON_SEARCH_REQUEST_BEFORE_REVIEW')
            if value['role']=='solver' and value['request_sha256'] not in allowed[value['window']]:
                raise RuntimeError('SOLVER_BOUNDARY_OR_MEMBERSHIP_MISMATCH')
            if value['role'] not in {'solver','reflection'}: raise RuntimeError('UNAUTHORIZED_ROLE')
            pending[number]=value;roles[value['role']]+=1;phases[value['phase']]+=1
        elif value['kind']=='RESPONSE_CHARGE':
            reservation=pending.pop(value['physical_attempt'])
            receipt=read(run/'responses'/f'{value["physical_attempt"]:06d}.json');response=receipt['response']
            if (digest(receipt['request'])!=reservation['request_sha256']
                or digest(response)!=value['response_sha256'] or not value['usage_reliable']
                or response['input_tokens']+response['output_tokens']!=value['amount']
                or not 0<=value['amount']<=reservation['amount']):
                raise RuntimeError('RESPONSE_OR_USAGE_MISMATCH')
            settled[value['role']]+=value['amount']
        elif value['kind']=='FAILURE_CHARGE': raise RuntimeError('UNEXPECTED_FAILURE_CHARGE')
        elif value['kind']=='CACHE_HIT':cache_hits+=1
    if pending:raise RuntimeError('UNSETTLED_REQUEST')
    accounting=audit_accounting(run);terminal=read(run/'completion.json')
    if (terminal['status']!='EXECUTION_ABORTED' or terminal['reason']!='OWNER_CONFORMANCE_REVIEW_NOT_PASS'
        or terminal['accounting']!=read(run/'accounting_snapshot.json')
        or terminal['accounting']['logical_evaluations']['baseline'] or terminal['accounting']['logical_evaluations']['audit']
        or (run/'full_metrics_progress.json').exists() or list(run.glob('window_*/baseline_full.json'))):
        raise RuntimeError('ABORT_RECEIPT_OR_PHASE_BOUNDARY_MISMATCH')
    solver=guard=0;window_rows=[];candidate_rows=[];failure_categories=Counter()
    for s in selections:
        proposals=read(run/f'window_{s["window"]}/proposals.json')
        if digest([{k:v for k,v in p.items() if k!='prompt'} for p in proposals])!=digest(s['proposal_audit']):
            raise RuntimeError('PROPOSAL_AUDIT_MISMATCH')
        metrics=actual_metrics=zeros=0
        for e in map(json.loads,(run/f'window_{s["window"]}/evaluations.jsonl').read_bytes().splitlines()):
            metrics+=len(e['ids'])
            if e['contract_valid']:actual_metrics+=len(e['ids'])
            else:zeros+=len(e['ids'])
        if (metrics!=s['native_metric_count'] or actual_metrics!=s['actual_solver_logical_evaluations']
            or zeros!=s['guard_rejection_metric_scores']):raise RuntimeError('SEARCH_METRIC_RECONCILIATION_MISMATCH')
        solver+=actual_metrics;guard+=zeros
        window_rows.append({'window':s['window'],'member':s['member'],'generated':len(proposals),
            'automatic_guard_passed':sum(p['contract_valid'] for p in proposals),
            'automatic_guard_rejected':sum(not p['contract_valid'] for p in proposals),
            'native_metric_scores':metrics,'solver_logical_evaluations':actual_metrics,'guard_zero_scores':zeros,
            'native_initial_score':s['native_initial_score'],'native_best_score':s['native_best_score'],
            'native_archive_count':s['native_archive_count'],'selected_for_full':len(s['selected']),'full_evaluated':0})
        for p in proposals:
            failure_categories.update(p['contract_failures'])
            candidate_rows.append({'window':s['window'],'member':s['member'],'generation':p['generation'],
                'prompt_hash':p['prompt_hash'],'automatic_guard_passed':p['contract_valid'],
                'automatic_guard_categories':p['contract_failures'],'full_evaluated':False,
                'member_improving':None,'v22_admissible':None})
    if solver!=terminal['accounting']['logical_evaluations']['search'] or sum(settled.values())!=accounting['charged_tokens']:
        raise RuntimeError('ACCOUNTING_TOTAL_MISMATCH')
    return {'identity':'MATH_GEPA_OWNER_REVIEW_ABORT_AUDIT_V1','attempt_identity':identity,
        'source_sha':frozen['source_sha'],'execution_status':'EXECUTION_ABORTED','scientific_status':'INVALID',
        'comparison_complete':False,'efficacy':'NOT_EVALUABLE','provider_calls_by_audit':0,
        'preservation_and_frozen_source':'PASS','journal_receipts_usage_and_zero_inflight':'PASS',
        'solver_shell_decoding_and_optimize_membership':'PASS','pre_full_barrier':'PASS',
        'automatic_semantic_conformance':'FAIL','confirmed_output_conflicts':1,'additional_unresolved_review_risks':3,
        'owner_review_issues':review['issues'],'original_files':len(actual),'original_inventory_sha256':digest(actual),
        'completion_sha256':file_hash(run/'completion.json'),'owner_review_sha256':rsha,
        'selection_hash':closed['selection_hash'],'charged_tokens':accounting['charged_tokens'],
        'physical_attempts':sum(roles.values()),'physical_attempts_by_role':dict(roles),
        'physical_attempts_by_phase':dict(phases),'role_charged_tokens':dict(settled),'reserved_inflight':0,
        'conservative_charge':0,'cache_hits':cache_hits,'last_event_sha256':previous,
        'native_metric_scores':solver+guard,'solver_logical_evaluations':solver,'guard_zero_scores':guard,
        'generated':len(candidate_rows),'automatic_guard_passed':sum(c['automatic_guard_passed'] for c in candidate_rows),
        'automatic_guard_rejected':sum(not c['automatic_guard_passed'] for c in candidate_rows),
        'contract_valid_after_owner_review':None,'selected_before_owner_review':sum(len(s['selected']) for s in selections),
        'full_evaluated':0,'member_improving':None,'v22_admissible':None,
        'unknown_full_outcomes':sum(len(s['selected']) for s in selections),'unmeasured_outcomes_are_unknown':True,
        'failure_categories':dict(failure_categories),'windows':window_rows,'candidates':candidate_rows,
        'shadow_calls':0,'validation_calls':0,'test_calls':0,'team_commits':0,
        'authorization_consumed':True,'automatic_retry_authorized':False,'invoice_cost':'NOT_AVAILABLE'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('run','bundle','seal','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    for name in list(os.environ):
        if 'API_KEY' in name or 'BASE_URL' in name:os.environ.pop(name,None)
    def blocked(*args,**kwargs):raise RuntimeError('OFFLINE_NETWORK_FORBIDDEN')
    socket.socket.connect=socket.socket.connect_ex=socket.create_connection=socket.getaddrinfo=blocked
    result=audit(a.run.resolve(),a.bundle.resolve(),a.seal.resolve());write(a.output,result)
    if audit_public_paths([a.output]):raise RuntimeError('SANITIZATION_FAILED')
    print(f'PASS preserved aborted-run audit; charged={result["charged_tokens"]}; Full=0; scientific=INVALID')


if __name__=='__main__':main()
