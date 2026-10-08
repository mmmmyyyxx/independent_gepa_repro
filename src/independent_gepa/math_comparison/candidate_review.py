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


def decision(request: dict[str,Any],status: str,categories: list[str]) -> dict[str,Any]:
    """Record the owner's already-made decision, without deciding it here."""
    value={'identity':RECEIPT_ID,'request_sha256':digest(request),
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
    if (value.get('status') not in {'PASS','REJECT'}
        or not isinstance(categories,list) or categories!=sorted(set(categories))
        or any(not isinstance(c,str) or not c or not c.replace('_','').isalnum() or c!=c.upper() for c in categories)
        or (value['status']=='PASS' and categories) or (value['status']=='REJECT' and not categories)
        or value.get('review_scope')!='immutable_interface_and_training_source_conformance_only'
        or value.get('prompt_and_source_provenance_reviewed') is not True
        or value.get('quality_selection_used') is not False
        or value.get('full_outcomes_read') is not False or value.get('candidate_outcomes_read') is not False):
        raise ProtocolViolation('CANDIDATE_OWNER_DECISION_SCOPE_MISMATCH')


class CandidateReview:
    def __init__(self,private: Path,identity: str,window: int,member: int,
                 examples: list[dict[str,Any]],shell: dict[str,str],timeout_seconds: int=900):
        self.private=private/'candidate_reviews';self.identity=identity;self.window=window;self.member=member
        self.examples=examples;self.shell=shell;self.timeout_seconds=timeout_seconds
        self.requests: dict[str,dict[str,Any]]={};self.receipts: dict[str,dict[str,Any]]={}

    def request(self,prompt: str,prompt_sha: str,generation: int,source_ids: list[str]) -> dict[str,Any]:
        if hashlib.sha256(prompt.encode('utf-8')).hexdigest()!=prompt_sha:
            raise ExecutionAbort('CANDIDATE_REVIEW_PROMPT_HASH_MISMATCH')
        source_set=set(source_ids)
        if len(source_set)!=len(source_ids) or not source_set<={e['example_id'] for e in self.examples}:
            raise ExecutionAbort('CANDIDATE_REVIEW_PROVENANCE_MISMATCH')
        return {'identity':REQUEST_ID,'attempt_identity':self.identity,'window':self.window,'member':self.member,
            'prompt_hash':prompt_sha,'prompt':prompt,'generation_first_seen':generation,'candidate_guard':GUARD_ID,
            'reflection_source_ids':source_ids,
            'reflection_source_records':[e for e in self.examples if e['example_id'] in source_set],
            'optimize_membership_sha256':digest(self.examples),'immutable_solver_shell':self.shell,
            'immutable_solver_shell_sha256':digest(self.shell),
            'required_scope':'immutable_interface_and_training_source_conformance_only',
            'no_candidate_outcomes_exist':True,'full_outcomes_read':False}

    def _wait_receipt(self,path: Path) -> dict[str,Any]:
        deadline=time.monotonic()+self.timeout_seconds
        while not path.exists():
            if time.monotonic()>=deadline:raise ExecutionAbort('CANDIDATE_OWNER_REVIEW_TIMEOUT')
            time.sleep(1)
        return read(path)

    def check(self,prompt: str,prompt_sha: str,generation: int,source_ids: list[str]) -> dict[str,Any]:
        if prompt_sha in self.receipts:
            # Reverify persisted decisions before every repeated/native/Full use.
            request=read(self.private/f'{prompt_sha}.request.json')
            value=read(self.private/f'{prompt_sha}.decision.json')
            if request!=self.requests[prompt_sha] or value!=self.receipts[prompt_sha]:
                raise ExecutionAbort('CANDIDATE_OWNER_RECEIPT_MUTATED')
            try:verify_decision(value,request)
            except ProtocolViolation as exc:raise ExecutionAbort(str(exc)) from exc
            return copy.deepcopy(value)
        request=self.request(prompt,prompt_sha,generation,source_ids)
        self.private.mkdir(parents=True,exist_ok=True)
        request_path=self.private/f'{prompt_sha}.request.json';path=self.private/f'{prompt_sha}.decision.json'
        if request_path.exists() or path.exists():raise ExecutionAbort('FRESH_CANDIDATE_OWNER_REVIEW_REQUIRED')
        write(request_path,request);self.requests[prompt_sha]=request
        print(f'CANDIDATE_OWNER_REVIEW_WAIT window={self.window} member={self.member} hash={prompt_sha}; no candidate Solver request',flush=True)
        value=self._wait_receipt(path)
        try:verify_decision(value,request)
        except ProtocolViolation as exc:raise ExecutionAbort(str(exc)) from exc
        self.receipts[prompt_sha]=copy.deepcopy(value)
        print(f'CANDIDATE_OWNER_REVIEW_{value["status"]} window={self.window} hash={prompt_sha}',flush=True)
        return value


def record_decision(request_path: Path,status: str,categories: list[str]) -> Path:
    """Owner CLI helper; refuse overwriting a decision or modifying a request."""
    request=read(request_path)
    if request.get('identity')!=REQUEST_ID or request.get('candidate_guard')!=GUARD_ID:
        raise ProtocolViolation('CANDIDATE_REVIEW_REQUEST_IDENTITY_MISMATCH')
    if hashlib.sha256(request['prompt'].encode('utf-8')).hexdigest()!=request['prompt_hash']:
        raise ProtocolViolation('CANDIDATE_REVIEW_TEXT_HASH_MISMATCH')
    path=request_path.with_name(request_path.name.replace('.request.json','.decision.json'))
    if not request_path.name.endswith('.request.json') or path==request_path or path.exists():
        raise ProtocolViolation('FRESH_CANDIDATE_DECISION_REQUIRED')
    value=decision(request,status,categories)
    # Publish a complete receipt in one rename; the waiting process never sees a
    # half-written JSON file. One tracked-code/owner writer controls this path.
    temporary=path.with_suffix('.pending')
    if temporary.exists():raise ProtocolViolation('CANDIDATE_DECISION_PENDING_EXISTS')
    write(temporary,value);temporary.replace(path)
    return path
