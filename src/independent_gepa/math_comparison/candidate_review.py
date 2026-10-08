"""Private owner conformance decisions before changed procedures reach Solver.

This gate checks contract/provenance only. It cannot rank candidates, change
their text, or use correctness scores. GEPA retains its native search decisions.
"""
from __future__ import annotations

from pathlib import Path
import copy
import hashlib
import time
from typing import Any

from ..protocol import ProtocolViolation
from .candidate_guard import GUARD_ID
from .contract import digest, read, write
from .runtime import ExecutionAbort

POLICY = 'owner_semantic_before_solver_v1'
REQUEST_ID = 'MATH_GEPA_PROPOSAL_CONFORMANCE_REQUEST_V1'
RECEIPT_ID = 'MATH_GEPA_PROPOSAL_CONFORMANCE_DECISION_V1'
REVIEW_CHECKS=('immutable_interface','source_provenance','inference_available_inputs','reusable_procedure')


def verify_request(request: dict[str,Any],examples: list[dict[str,Any]]|None=None,shell: dict[str,str]|None=None) -> None:
    if (request.get('identity')!=REQUEST_ID or request.get('candidate_guard')!=GUARD_ID
        or not isinstance(request.get('attempt_identity'),str) or not request['attempt_identity']
        or type(request.get('window')) is not int or not 0<=request['window']<7
        or type(request.get('member')) is not int or not 0<=request['member']<5
        or not isinstance(request.get('reviewer_identity'),str) or not request['reviewer_identity']
        or hashlib.sha256(request.get('prompt','').encode('utf-8')).hexdigest()!=request.get('prompt_hash')
        or digest(request.get('immutable_solver_shell'))!=request.get('immutable_solver_shell_sha256')
        or request.get('required_scope')!='immutable_interface_and_training_source_conformance_only'
        or request.get('no_candidate_outcomes_exist') is not True or request.get('full_outcomes_read') is not False):
        raise ProtocolViolation('CANDIDATE_REVIEW_REQUEST_IDENTITY_MISMATCH')
    ids=request.get('reflection_source_ids',[]);records=request.get('reflection_source_records',[])
    if (not isinstance(ids,list) or not isinstance(records,list) or len(ids)!=len(set(ids))
        or len(records)!=len(ids) or {r['example_id'] for r in records}!=set(ids)):
        raise ProtocolViolation('CANDIDATE_REVIEW_SOURCE_ID_RECORD_MISMATCH')
    if examples is not None:
        by_id={e['example_id']:e for e in examples}
        if (digest(examples)!=request.get('optimize_membership_sha256')
            or any(by_id.get(r['example_id'])!=r for r in records)):
            raise ProtocolViolation('CANDIDATE_REVIEW_SOURCE_MEMBERSHIP_MISMATCH')
    if shell is not None and request['immutable_solver_shell']!=shell:
        raise ProtocolViolation('CANDIDATE_REVIEW_IMMUTABLE_SHELL_MISMATCH')


def decision(request: dict[str,Any],status: str,categories: list[str],*,reviewer: str|None=None,
             notes: dict[str,Any]|None=None) -> dict[str,Any]:
    """Record the owner's already-made decision, without deciding it here."""
    verify_request(request)
    reviewer=reviewer or 'offline_fixture'
    if notes is None and request['reviewer_identity']=='offline_fixture':
        notes={'checks':{c:'RESOLVED' if status=='PASS' else 'REJECTED' for c in REVIEW_CHECKS},
               'rationale':'Synthetic deterministic unit fixture; not an actual experiment review.'}
    value={'identity':RECEIPT_ID,'request_sha256':digest(request),'reviewer_identity':reviewer,
        'review_attestation':notes,'review_attestation_sha256':digest(notes),
        **{k:request[k] for k in ('attempt_identity','window','member','prompt_hash','candidate_guard')},
        'status':status,'categories':sorted(set(categories)),
        'review_scope':'immutable_interface_and_training_source_conformance_only',
        'prompt_and_source_provenance_reviewed':True,'quality_selection_used':False,
        'full_outcomes_read':False,'candidate_outcomes_read':False}
    value['receipt_sha256']=digest(value)
    verify_decision(value,request)
    return value


def verify_decision(value: dict[str,Any],request: dict[str,Any]) -> None:
    check=dict(value);sha=check.pop('receipt_sha256',None)
    if (digest(check)!=sha or value.get('identity')!=RECEIPT_ID
        or value.get('request_sha256')!=digest(request)
        or any(value.get(k)!=request[k] for k in ('attempt_identity','window','member','prompt_hash','candidate_guard'))):
        raise ProtocolViolation('CANDIDATE_OWNER_DECISION_IDENTITY_MISMATCH')
    categories=value.get('categories')
    notes=value.get('review_attestation')
    if (value.get('status') not in {'PASS','REJECT'}
        or not isinstance(categories,list) or categories!=sorted(set(categories))
        or any(not isinstance(c,str) or not c or not c.replace('_','').isalnum() or c!=c.upper() for c in categories)
        or (value['status']=='PASS' and categories) or (value['status']=='REJECT' and not categories)
        or value.get('review_scope')!='immutable_interface_and_training_source_conformance_only'
        or value.get('prompt_and_source_provenance_reviewed') is not True
        or value.get('quality_selection_used') is not False
        or value.get('full_outcomes_read') is not False or value.get('candidate_outcomes_read') is not False
        or value.get('reviewer_identity')!=request['reviewer_identity']
        or not isinstance(notes,dict) or digest(notes)!=value.get('review_attestation_sha256')
        or not isinstance(notes.get('rationale'),str) or len(notes['rationale'].strip())<20
        or not isinstance(notes.get('checks'),dict) or set(notes['checks'])!=set(REVIEW_CHECKS)
        or any(c not in {'RESOLVED','REJECTED','UNRESOLVED'} for c in notes['checks'].values())
        or (value['status']=='PASS' and any(c!='RESOLVED' for c in notes['checks'].values()))):
        raise ProtocolViolation('CANDIDATE_OWNER_DECISION_SCOPE_MISMATCH')


class CandidateReview:
    def __init__(self,private: Path,identity: str,window: int,member: int,
                 examples: list[dict[str,Any]],shell: dict[str,str],timeout_seconds: int=900,
                 reviewer_identity: str='offline_fixture'):
        self.private=private/'candidate_reviews';self.identity=identity;self.window=window;self.member=member
        self.examples=examples;self.shell=shell;self.timeout_seconds=timeout_seconds
        self.reviewer_identity=reviewer_identity
        self.requests: dict[str,dict[str,Any]]={};self.receipts: dict[str,dict[str,Any]]={}

    def request(self,prompt: str,prompt_sha: str,generation: int,source_ids: list[str]) -> dict[str,Any]:
        if hashlib.sha256(prompt.encode('utf-8')).hexdigest()!=prompt_sha:
            raise ExecutionAbort('CANDIDATE_REVIEW_PROMPT_HASH_MISMATCH')
        source_set=set(source_ids)
        if len(source_set)!=len(source_ids) or not source_set<={e['example_id'] for e in self.examples}:
            raise ExecutionAbort('CANDIDATE_REVIEW_PROVENANCE_MISMATCH')
        value={'identity':REQUEST_ID,'attempt_identity':self.identity,'window':self.window,'member':self.member,
            'reviewer_identity':self.reviewer_identity,
            'prompt_hash':prompt_sha,'prompt':prompt,'generation_first_seen':generation,'candidate_guard':GUARD_ID,
            'reflection_source_ids':source_ids,
            'reflection_source_records':[e for e in self.examples if e['example_id'] in source_set],
            'optimize_membership_sha256':digest(self.examples),'immutable_solver_shell':self.shell,
            'immutable_solver_shell_sha256':digest(self.shell),
            'required_scope':'immutable_interface_and_training_source_conformance_only',
            'no_candidate_outcomes_exist':True,'full_outcomes_read':False}
        verify_request(value,self.examples,self.shell)
        return value

    def _wait_receipt(self,path: Path) -> dict[str,Any]:
        deadline=time.monotonic()+self.timeout_seconds
        while not path.exists():
            if time.monotonic()>=deadline:raise ExecutionAbort('CANDIDATE_OWNER_REVIEW_TIMEOUT')
            time.sleep(1)
        return read(path)

    def check(self,prompt: str,prompt_sha: str,generation: int,source_ids: list[str]) -> dict[str,Any]:
        if hashlib.sha256(prompt.encode('utf-8')).hexdigest()!=prompt_sha:
            raise ExecutionAbort('CANDIDATE_REVIEW_PROMPT_HASH_MISMATCH')
        if len(source_ids)!=len(set(source_ids)) or not set(source_ids)<={e['example_id'] for e in self.examples}:
            raise ExecutionAbort('CANDIDATE_REVIEW_PROVENANCE_MISMATCH')
        if prompt_sha in self.receipts:
            # Reverify persisted decisions before every repeated/native/Full use.
            request=read(self.private/f'{prompt_sha}.request.json')
            value=read(self.private/f'{prompt_sha}.decision.json')
            if request!=self.requests[prompt_sha] or value!=self.receipts[prompt_sha]:
                raise ExecutionAbort('CANDIDATE_OWNER_RECEIPT_MUTATED')
            try:
                verify_request(request,self.examples,self.shell);verify_decision(value,request)
            except ProtocolViolation as exc:raise ExecutionAbort(str(exc)) from exc
            return copy.deepcopy(value)
        request=self.request(prompt,prompt_sha,generation,source_ids)
        self.private.mkdir(parents=True,exist_ok=True)
        request_path=self.private/f'{prompt_sha}.request.json';path=self.private/f'{prompt_sha}.decision.json'
        if request_path.exists() or path.exists():raise ExecutionAbort('FRESH_CANDIDATE_OWNER_REVIEW_REQUIRED')
        write(request_path,request);self.requests[prompt_sha]=request
        print(f'CANDIDATE_OWNER_REVIEW_WAIT window={self.window} member={self.member} hash={prompt_sha}; no candidate Solver request',flush=True)
        value=self._wait_receipt(path)
        if read(request_path)!=request:raise ExecutionAbort('CANDIDATE_OWNER_REQUEST_MUTATED_WHILE_WAITING')
        try:
            verify_request(request,self.examples,self.shell);verify_decision(value,request)
        except ProtocolViolation as exc:raise ExecutionAbort(str(exc)) from exc
        self.receipts[prompt_sha]=copy.deepcopy(value)
        print(f'CANDIDATE_OWNER_REVIEW_{value["status"]} window={self.window} hash={prompt_sha}',flush=True)
        return value


def record_decision(request_path: Path,status: str,categories: list[str],*,reviewer: str|None=None,
                    notes: dict[str,Any]|None=None) -> Path:
    """Owner CLI helper; refuse overwriting a decision or modifying a request."""
    request=read(request_path)
    verify_request(request)
    if hashlib.sha256(request['prompt'].encode('utf-8')).hexdigest()!=request['prompt_hash']:
        raise ProtocolViolation('CANDIDATE_REVIEW_TEXT_HASH_MISMATCH')
    path=request_path.with_name(request_path.name.replace('.request.json','.decision.json'))
    if not request_path.name.endswith('.request.json') or path==request_path or path.exists():
        raise ProtocolViolation('FRESH_CANDIDATE_DECISION_REQUIRED')
    value=decision(request,status,categories,reviewer=reviewer,notes=notes)
    # Publish a complete receipt in one rename; the waiting process never sees a
    # half-written JSON file. One tracked-code/owner writer controls this path.
    temporary=path.with_suffix('.pending')
    if temporary.exists():raise ProtocolViolation('CANDIDATE_DECISION_PENDING_EXISTS')
    write(temporary,value);temporary.replace(path)
    return path
