"""A frozen, outcome-blind owner review barrier before independent Full audits."""
from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from ..protocol import ProtocolViolation
from .candidate_guard import GUARD_ID, candidate_valid
from .contract import digest, read
from .runtime import ExecutionAbort


def review_membership(selections: list[dict[str,Any]]) -> list[dict[str,Any]]:
    return [{'window':s['window'],'member':s['member'],'prompt_hash':r['prompt_hash']}
            for s in selections for r in s['selected']]


def generated_review_membership(selections: list[dict[str,Any]]) -> list[dict[str,Any]]:
    return [{'window':s['window'],'member':s['member'],'generation':r['generation'],'prompt_hash':r['prompt_hash']}
            for s in selections for r in s.get('proposal_audit',[]) if r['contract_valid']]


def verify_owner_review(value: dict[str,Any],identity: str,selections: list[dict[str,Any]]) -> None:
    check=dict(value);sha=check.pop('receipt_sha256',None)
    if digest(check)!=sha or value.get('attempt_identity')!=identity or value.get('selection_hash')!=digest(selections):
        raise ProtocolViolation('OWNER_CONFORMANCE_IDENTITY_MISMATCH')
    if (value.get('identity')!='MATH_GEPA_SELECTED_OWNER_CONFORMANCE_V1'
        or value.get('candidate_guard')!=GUARD_ID or value.get('status')!='PASS'
        or value.get('outcome_blind') is not True or value.get('full_outcomes_read') is not False
        or value.get('reviewed')!=review_membership(selections)
        or value.get('reviewed_generated_valid')!=generated_review_membership(selections)):
        raise ProtocolViolation('OWNER_CONFORMANCE_REVIEW_NOT_PASS')


def verify_final_release(private: Path,identity: str,selections: list[dict[str,Any]],reviewer: str) -> str:
    value=read(private/'owner_conformance.json');manifest=read(private/'outcome_blind_pool_manifest.json')
    verify_owner_review(value,identity,selections)
    check=dict(manifest);sha=check.pop('manifest_sha256',None);notes=value.get('review_attestation')
    if (digest(check)!=sha or value.get('pool_manifest_sha256')!=sha
        or manifest.get('attempt_identity')!=identity or manifest.get('selection_hash')!=digest(selections)
        or value.get('reviewer_identity')!=reviewer or manifest.get('reviewer_identity')!=reviewer
        or value.get('pre_solver_reconciliation')!='PASS' or digest(notes)!=value.get('review_attestation_sha256')
        or not isinstance(notes,dict) or notes.get('manifest_sha256')!=sha
        or notes.get('all_candidate_decisions_actually_reviewed') is not True
        or notes.get('complete_pool_and_selected_membership_checked') is not True
        or notes.get('full_outcomes_read') is not False or notes.get('search_scores_read') is not False
        or manifest.get('all_decisions_verified') is not True or manifest.get('no_unapproved_solver_dispatch') is not True):
        raise ProtocolViolation('FINAL_OWNER_PRE_SOLVER_RECONCILIATION_REQUIRED')
    return value['receipt_sha256']


def await_owner_review(private: Path,identity: str,selections: list[dict[str,Any]],examples: list[dict[str,Any]],
                       *,timeout_seconds: int=900,bundle: Path|None=None,reviewer: str|None=None) -> dict[str,Any]:
    if any(not candidate_valid(row['prompt'],examples) for s in selections for row in s['selected']):
        raise ExecutionAbort('FROZEN_SELECTED_CONFORMANCE_FAILURE')
    print('SEARCH_FROZEN_WAITING_FOR_OUTCOME_BLIND_OWNER_CONFORMANCE; no Full requests dispatched',flush=True)
    path=private/'owner_conformance.json';deadline=time.monotonic()+timeout_seconds
    while not path.exists():
        if time.monotonic()>=deadline: raise ExecutionAbort('OWNER_CONFORMANCE_REVIEW_TIMEOUT')
        time.sleep(1)
    value=read(path)
    try:
        verify_owner_review(value,identity,selections)
        if bundle is not None:
            from .pool_review import prepare_pool
            if read(private/'outcome_blind_pool_manifest.json')!=prepare_pool(private,bundle):
                raise ProtocolViolation('FINAL_POOL_RECONCILIATION_MISMATCH')
            verify_final_release(private,identity,selections,reviewer)
    except ProtocolViolation as exc:raise ExecutionAbort(str(exc)) from exc
    print('OWNER_CONFORMANCE_PASS; entering frozen independent Full audits',flush=True)
    return value
