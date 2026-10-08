from __future__ import annotations

import copy
import pytest

from independent_gepa.math_comparison.candidate_guard import GUARD_ID
from independent_gepa.math_comparison.conformance import verify_owner_review,review_membership,generated_review_membership,await_owner_review
from independent_gepa.math_comparison.contract import digest,write
from independent_gepa.math_comparison.funnel import candidate_funnel
from independent_gepa.math_comparison.runtime import ExecutionAbort
from independent_gepa.protocol import ProtocolViolation


def selections():
    return [{'window':0,'member':0,'native_best_hash':'initial','selected_hashes':['legal'],
        'selected':[{'prompt_hash':'legal','prompt':'Verify the result internally.'}],
        'proposal_audit':[{'generation':1,'prompt_hash':'illegal','contract_valid':False,'contract_failures':['SOURCE_ANSWER_LITERAL_COPY']},
            {'generation':2,'prompt_hash':'legal','contract_valid':True,'contract_failures':[]}]}]


def receipt(pool):
    value={'identity':'MATH_GEPA_SELECTED_OWNER_CONFORMANCE_V1','attempt_identity':'attempt',
        'selection_hash':digest(pool),'candidate_guard':GUARD_ID,'status':'PASS',
        'outcome_blind':True,'full_outcomes_read':False,'reviewed':review_membership(pool),
        'reviewed_generated_valid':generated_review_membership(pool)}
    return {**value,'receipt_sha256':digest(value)}


@pytest.mark.parametrize('change', ['missing_member','wrong_attempt','failed_review','read_outcomes','missing_generated'])
def test_owner_review_cannot_release_wrong_or_incomplete_membership(change):
    pool=selections();value=receipt(pool)
    if change=='missing_member': value['reviewed']=[]
    elif change=='wrong_attempt': value['attempt_identity']='different'
    elif change=='failed_review': value['status']='FAIL'
    elif change=='read_outcomes': value['full_outcomes_read']=True
    else:value['reviewed_generated_valid']=[]
    value.pop('receipt_sha256');value['receipt_sha256']=digest(value)
    with pytest.raises(ProtocolViolation):verify_owner_review(value,'attempt',pool)


def test_owner_barrier_waits_without_a_transport_or_audit(tmp_path):
    pool=selections();examples=[{'problem':'synthetic problem','reference':'1'}]
    with pytest.raises(ExecutionAbort,match='OWNER_CONFORMANCE_REVIEW_TIMEOUT'):
        await_owner_review(tmp_path,'attempt',pool,examples,timeout_seconds=0)
    write(tmp_path/'owner_conformance.json',receipt(pool))
    assert await_owner_review(tmp_path,'attempt',pool,examples)['status']=='PASS'


def test_funnel_preserves_invalid_and_unknown_and_does_not_announce_scientific_validity():
    pool=selections();before=candidate_funnel(pool,[])
    assert (before['generated'],before['contract_valid'],before['contract_invalid'],before['full_evaluated'])==(2,1,1,0)
    assert all(r['member_improving'] is None for r in before['candidates'])
    measured=[{'window':0,'prompt_hash':'legal','candidate_member_correct':25,'fresh_parent_delta':3,
               'v22_admissible':True,'PURE_REPAIR':True}]
    after=candidate_funnel(pool,measured)
    assert (after['full_evaluated'],after['member_improving'],after['v22_admissible'],after['pure_repairs'])==(1,1,1,1)
    assert after['candidates'][0]['full_evaluated'] is False and after['candidates'][0]['v22_admissible'] is None


def test_full_measurement_cannot_silently_cover_an_invalid_or_unselected_procedure():
    pool=selections()
    row={'window':0,'prompt_hash':'unknown','candidate_member_correct':60,'fresh_parent_delta':38,
         'v22_admissible':True,'PURE_REPAIR':True}
    with pytest.raises(ProtocolViolation):candidate_funnel(pool,[row])
    row['prompt_hash']='illegal';pool[0]['selected'].append({'prompt_hash':'illegal'});pool[0]['selected_hashes'].append('illegal')
    with pytest.raises(ProtocolViolation):candidate_funnel(pool,[row])
