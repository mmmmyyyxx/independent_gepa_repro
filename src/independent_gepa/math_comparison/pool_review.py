"""Mechanical reconciliation projected without search scores or Full outcomes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..protocol import ProtocolViolation
from .candidate_guard import GUARD_ID,candidate_failures
from .candidate_review import verify_request,verify_decision
from .contract import read,write,digest
from .conformance import review_membership,generated_review_membership,verify_owner_review
from .search import INITIAL,prompt_hash
from .runtime import Runtime


def prepare_pool(run: Path,bundle: Path) -> dict[str,Any]:
    frozen=read(run/'frozen_attempt.json');closed=read(run/'SEARCH_COMPLETE.json')
    identity=frozen['identity'];config=frozen['config'];selections=closed['selections']
    if (closed['identity']!=identity or digest(selections)!=closed['selection_hash']
        or len(selections)!=7 or closed['search_closed_forever'] is not True or closed['audit_started'] is not False):
        raise ProtocolViolation('POOL_SEARCH_FREEZE_MISMATCH')
    if (list(run.glob('window_*/baseline_full.json')) or list(run.glob('window_*/full_*.json'))
        or (run/'full_metrics_progress.json').exists() or (run/'candidate_metrics.json').exists()):
        raise ProtocolViolation('POOL_REVIEW_MUST_PRECEDE_FULL')
    examples=read(bundle/'optimize.json');shell=read(bundle/'shell.json');records=[];decisions={};texts={}
    reviewer=config['reviewer_identity']
    for window,s in enumerate(selections):
        member=config['target_schedule'][window]
        if s['window']!=window or s['member']!=member:raise ProtocolViolation('POOL_WINDOW_MEMBER_MISMATCH')
        private=run/f'window_{window}';proposals=read(private/'proposals.json')
        if [{k:v for k,v in p.items() if k!='prompt'} for p in proposals]!=s['proposal_audit']:
            raise ProtocolViolation('POOL_PROPOSAL_AUDIT_MISMATCH')
        texts[window]={prompt_hash(INITIAL):INITIAL}
        expected_requests=set()
        for generation,p in enumerate(proposals,1):
            sha=prompt_hash(p['prompt']);lexical=candidate_failures(p['prompt'],examples)
            if p['generation']!=generation or p['prompt_hash']!=sha or p['automatic_guard_passed']!=(not bool(lexical)):
                raise ProtocolViolation('POOL_GENERATION_OR_LEXICAL_MISMATCH')
            texts[window][sha]=p['prompt']
            row={'window':window,'member':member,'generation':generation,'prompt_hash':sha,
                 'contract_valid':p['contract_valid'],'owner_review_status':p['owner_review_status']}
            if lexical:
                if p['contract_valid'] or p['owner_review_status']!='LEXICAL_REJECTED' or p['contract_failures']!=lexical:
                    raise ProtocolViolation('POOL_LEXICAL_DECISION_MISMATCH')
                row['categories']=lexical
            elif p['prompt']==INITIAL:
                if not p['contract_valid'] or p['owner_review_status']!='IMMUTABLE_INITIAL':
                    raise ProtocolViolation('POOL_INITIAL_CONFORMANCE_MISMATCH')
                row['categories']=[]
            else:
                expected_requests.add(sha)
                request=read(private/'candidate_reviews'/f'{sha}.request.json')
                value=read(private/'candidate_reviews'/f'{sha}.decision.json')
                verify_request(request,examples,shell);verify_decision(value,request)
                if (request['attempt_identity']!=identity or request['window']!=window or request['member']!=member
                    or request['prompt']!=p['prompt'] or request['reviewer_identity']!=reviewer
                    or p['owner_receipt_sha256']!=value['receipt_sha256']
                    or p['owner_review_status']!=value['status'] or p['contract_valid']!=(value['status']=='PASS')):
                    raise ProtocolViolation('POOL_SEMANTIC_DECISION_MISMATCH')
                expected=[] if value['status']=='PASS' else ['OWNER_CONFORMANCE_'+c for c in value['categories']]
                if p['contract_failures']!=expected:raise ProtocolViolation('POOL_SEMANTIC_CATEGORY_MISMATCH')
                decisions[(window,sha)]=value
                row.update({k:value[k] for k in ('reviewer_identity','receipt_sha256','request_sha256','review_attestation_sha256','categories')})
            records.append(row)
        actual={p.name.removesuffix('.request.json') for p in (private/'candidate_reviews').glob('*.request.json')}
        actual_decisions={p.name.removesuffix('.decision.json') for p in (private/'candidate_reviews').glob('*.decision.json')}
        if actual!=expected_requests or actual_decisions!=expected_requests:
            raise ProtocolViolation('POOL_ORPHAN_OR_MISSING_REVIEW')
        for row in s['selected']:
            if (row['prompt_hash']!=prompt_hash(row['prompt']) or row['prompt_hash']==prompt_hash(INITIAL)
                or (window,row['prompt_hash']) not in decisions or decisions[(window,row['prompt_hash'])]['status']!='PASS'):
                raise ProtocolViolation('POOL_SELECTED_WITHOUT_APPROVAL')
        if s['selected_hashes']!=[p['prompt_hash'] for p in s['selected']]:
            raise ProtocolViolation('POOL_SELECTION_MEMBERSHIP_MISMATCH')
    prototype=Runtime.__new__(Runtime);prototype.models=read(bundle/'model_contract.json')
    allowed={};allowed_cache={}
    for window,prompts in texts.items():
        member=config['target_schedule'][window]
        for sha,prompt in prompts.items():
            for e in examples:
                req=prototype.request('solver',[{'role':'system','content':shell['system']},
                    {'role':'user','content':prompt+'\n\n'+e['problem']+shell['suffix']}])
                allowed[(window,digest(req))]=sha
                allowed_cache[(window,digest({'attempt':identity,'window':window,'member':member,'request':req}))]=sha
    previous='0'*64;approved=set();dispatches=0
    for event in map(json.loads,(run/'accounting.jsonl').read_bytes().splitlines()):
        value=dict(event);sha=value.pop('event_sha256')
        if digest(value)!=sha or value['previous_event_sha256']!=previous:raise ProtocolViolation('POOL_JOURNAL_CHAIN_MISMATCH')
        previous=sha
        if value['kind']=='CANDIDATE_REVIEW_DECISION':
            key=(value['window'],value['prompt_hash']);receipt=decisions.get(key)
            if receipt is None or any(value.get(k)!=receipt[k] for k in ('status','receipt_sha256','request_sha256','reviewer_identity')):
                raise ProtocolViolation('POOL_PRE_SOLVER_REVIEW_EVENT_MISMATCH')
            if receipt['status']=='PASS':approved.add(key)
        elif value['kind'] in {'RESERVE','CACHE_HIT'}:
            if value['phase']!='search':raise ProtocolViolation('POOL_PAID_FULL_BEFORE_REVIEW')
            if value['role']!='solver':continue
            window=value['window']
            if value['kind']=='RESERVE':
                receipt=read(run/'requests'/f'{value["physical_attempt"]:06d}.json')
                if digest(receipt['request'])!=value['request_sha256']:raise ProtocolViolation('POOL_WIRE_REQUEST_MISMATCH')
                ph=allowed.get((window,value['request_sha256']));dispatches+=1
            else:ph=allowed_cache.get((window,value['key']))
            if ph is None or (ph!=prompt_hash(INITIAL) and (window,ph) not in approved):
                raise ProtocolViolation('POOL_UNAPPROVED_PROCEDURE_REACHED_SOLVER')
    if previous!=closed['search_accounting']['last_event_sha256']:
        raise ProtocolViolation('POOL_SEARCH_JOURNAL_SEAL_MISMATCH')
    value={'identity':'MATH_GEPA_OUTCOME_BLIND_POOL_MANIFEST_V1','attempt_identity':identity,
        'selection_hash':closed['selection_hash'],'candidate_guard':GUARD_ID,'reviewer_identity':reviewer,
        'reviewed':review_membership(selections),'reviewed_generated_valid':generated_review_membership(selections),
        'complete_generated_membership':records,'all_decisions_verified':True,
        'no_unapproved_solver_dispatch':True,'solver_dispatch_count_checked':dispatches,
        'full_outcomes_read':False,'search_scores_disclosed':False,'journal_prefix_sha256':previous}
    value['manifest_sha256']=digest(value)
    return value


def finalize_pool(run: Path,bundle: Path,reviewer: str,notes: dict[str,Any]) -> dict[str,Any]:
    manifest=prepare_pool(run,bundle)
    if (reviewer!=manifest['reviewer_identity'] or notes.get('manifest_sha256')!=manifest['manifest_sha256']
        or notes.get('all_candidate_decisions_actually_reviewed') is not True
        or notes.get('complete_pool_and_selected_membership_checked') is not True
        or notes.get('full_outcomes_read') is not False or notes.get('search_scores_read') is not False
        or not isinstance(notes.get('rationale'),str) or len(notes['rationale'].strip())<20):
        raise ProtocolViolation('FINAL_OWNER_ATTESTATION_REQUIRED')
    value={'identity':'MATH_GEPA_SELECTED_OWNER_CONFORMANCE_V1','attempt_identity':manifest['attempt_identity'],
        'selection_hash':manifest['selection_hash'],'candidate_guard':GUARD_ID,'status':'PASS',
        'outcome_blind':True,'full_outcomes_read':False,'reviewed':manifest['reviewed'],
        'reviewed_generated_valid':manifest['reviewed_generated_valid'],'reviewer_identity':reviewer,
        'pool_manifest_sha256':manifest['manifest_sha256'],'review_attestation':notes,
        'review_attestation_sha256':digest(notes),'pre_solver_reconciliation':'PASS'}
    value['receipt_sha256']=digest(value)
    verify_owner_review(value,manifest['attempt_identity'],read(run/'SEARCH_COMPLETE.json')['selections'])
    path=run/'owner_conformance.json'
    if path.exists():raise ProtocolViolation('FINAL_OWNER_RECEIPT_ALREADY_EXISTS')
    write(run/'outcome_blind_pool_manifest.json',manifest)
    temporary=run/'owner_conformance.pending';write(temporary,value);temporary.replace(path)
    return value
