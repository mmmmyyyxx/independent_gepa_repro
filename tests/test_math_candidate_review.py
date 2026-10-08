from __future__ import annotations

from pathlib import Path
import pytest

from independent_gepa.math_comparison.candidate_review import CandidateReview,decision,record_decision,verify_decision
from independent_gepa.math_comparison.contract import load_config,read,write,digest
from independent_gepa.math_comparison.runtime import ExecutionAbort
from independent_gepa.math_comparison.search import MathAdapter,INITIAL,prompt_hash,run_window,REFLECTION_TEMPLATE
from independent_gepa.math_comparison.funnel import candidate_funnel
from independent_gepa.protocol import ProtocolViolation
from tests.test_math_comparison import Fake,runtime

ROOT=Path(__file__).resolve().parents[1]
ROWS=[{'example_id':'e1','problem':'A synthetic arithmetic problem.','reference':'1'}]
SHELL={'system':'Exactly one visible final line.','suffix':'No other visible text.'}
PROMPT='Check signs and boundary conditions internally.'


def broker(path,window=0,member=0):
    return CandidateReview(path,'attempt',window,member,ROWS,SHELL,timeout_seconds=0)


def prepared(b,status='PASS',categories=None):
    request=b.request(PROMPT,prompt_hash(PROMPT),1,['e1'])
    path=b.private/f'{prompt_hash(PROMPT)}.request.json'
    write(path,request)
    record_decision(path,status,categories or [])
    return request,read(path.with_name(path.name.replace('.request.json','.decision.json')))


@pytest.mark.parametrize('change',['hash','attempt','window','member','outcomes','quality','missing_scope'])
def test_owner_decision_cannot_be_rebound_or_used_for_quality_selection(tmp_path,change):
    b=broker(tmp_path);request,value=prepared(b)
    if change in {'attempt','window','member','hash'}:
        key={'attempt':'attempt_identity','hash':'prompt_hash'}.get(change,change)
        value[key]='wrong'
    elif change=='outcomes':value['candidate_outcomes_read']=True
    elif change=='quality':value['quality_selection_used']=True
    else:value.pop('prompt_and_source_provenance_reviewed')
    value.pop('receipt_sha256');value['receipt_sha256']=digest(value)
    with pytest.raises(ProtocolViolation):verify_decision(value,request)


def test_missing_decision_times_out_before_any_changed_solver(tmp_path):
    class NoSolver:
        def solve(self,*args):raise AssertionError('Unreviewed candidate reached Solver')
    adapter=MathAdapter(NoSolver(),ROWS,0,0,tmp_path,review=broker(tmp_path))
    with pytest.raises(ExecutionAbort,match='CANDIDATE_OWNER_REVIEW_TIMEOUT'):
        adapter.evaluate(ROWS,{'system_prompt':PROMPT})
    assert adapter.metrics_used==0 and not adapter.evaluated


def auto_decisions(monkeypatch,status='PASS',categories=None):
    def write_before_release(self,path):
        request_path=path.with_name(path.name.replace('.decision.json','.request.json'))
        record_decision(request_path,status,categories or [])
        return read(path)
    monkeypatch.setattr(CandidateReview,'_wait_receipt',write_before_release)


def test_semantic_rejection_blocks_solver_and_consumes_native_metric_budget(tmp_path,monkeypatch):
    class NoSolver:
        def solve(self,*args):raise AssertionError('Semantically rejected candidate reached Solver')
    auto_decisions(monkeypatch,'REJECT',['UNRESOLVED_SOURCE_SPECIFIC_RESULT'])
    adapter=MathAdapter(NoSolver(),ROWS,0,0,tmp_path,review=broker(tmp_path))
    adapter.reflection_source_ids=['e1']
    batch=adapter.evaluate(ROWS,{'system_prompt':PROMPT},True)
    assert batch.scores==[0.0] and adapter.metrics_used==1 and not adapter.evaluated
    checked=adapter.check_candidate(PROMPT)
    assert checked['automatic_guard_passed'] and checked['owner_review_status']=='REJECT'
    assert checked['contract_failures']==['OWNER_CONFORMANCE_UNRESOLVED_SOURCE_SPECIFIC_RESULT']


def test_pass_is_bound_to_source_and_reused_only_in_the_same_window(tmp_path,monkeypatch):
    auto_decisions(monkeypatch);b=broker(tmp_path)
    value=b.check(PROMPT,prompt_hash(PROMPT),1,['e1'])
    request=read(b.private/f'{prompt_hash(PROMPT)}.request.json')
    assert request['reflection_source_records']==ROWS and request['immutable_solver_shell']==SHELL
    assert 'scores' not in request and 'responses' not in request
    assert b.check(PROMPT,prompt_hash(PROMPT),2,[])==value
    other=broker(tmp_path/'other',window=1)
    changed=other.request(PROMPT,prompt_hash(PROMPT),1,['e1'])
    with pytest.raises(ProtocolViolation):verify_decision(value,changed)
    value['categories']=['MUTATED'];write(b.private/f'{prompt_hash(PROMPT)}.decision.json',value)
    with pytest.raises(ExecutionAbort,match='MUTATED'):b.check(PROMPT,prompt_hash(PROMPT),3,[])


def test_decision_cannot_overwrite_receipt_or_approve_unresolved_categories(tmp_path):
    b=broker(tmp_path);request,value=prepared(b)
    with pytest.raises(ProtocolViolation,match='FRESH_CANDIDATE_DECISION'):
        record_decision(b.private/f'{prompt_hash(PROMPT)}.request.json','PASS',[])
    with pytest.raises(ProtocolViolation):decision(request,'PASS',['UNRESOLVED'])
    with pytest.raises(ProtocolViolation):decision(request,'REJECT',[])
    with pytest.raises(ExecutionAbort):b.request(PROMPT,prompt_hash(PROMPT),1,['heldout'])


def test_direct_solver_cannot_bypass_review_via_cache_or_full_phase(tmp_path):
    fake=Fake();rt=runtime(tmp_path,fake)
    rt.config=load_config(ROOT/'configs/math_a4_matched_guard_repair_v4.yaml')
    for phase in ('search','audit','baseline'):
        with pytest.raises(ExecutionAbort,match='UNAPPROVED_CHANGED'):
            rt.solve(PROMPT,{'problem':'index=0','reference':'1'},0,0,phase)
    assert not fake.requests and rt.logical=={'search':0,'audit':0,'baseline':0}


def test_approved_solver_and_full_cache_use_recheck_the_same_receipt(tmp_path,monkeypatch):
    auto_decisions(monkeypatch);fake=Fake();rt=runtime(tmp_path,fake)
    rt.config=load_config(ROOT/'configs/math_a4_matched_guard_repair_v4.yaml')
    rows=[{'example_id':'e1','problem':'index=0','reference':'1'}]
    b=CandidateReview(tmp_path/'window_0',rt.identity,0,0,rows,rt.shell,0)
    adapter=MathAdapter(rt,rows,0,0,tmp_path,review=b);adapter.reflection_source_ids=['e1']
    rt.candidate_checks[(0,0)]=adapter.check_candidate
    assert adapter.evaluate(rows,{'system_prompt':PROMPT}).scores==[1.0]
    assert rt.solve(PROMPT,rows[0],0,0,'audit')['correct'] and rt.cache_hits==1
    assert len(fake.requests)==1
    value=read(b.private/f'{prompt_hash(PROMPT)}.decision.json');value['status']='REJECT'
    write(b.private/f'{prompt_hash(PROMPT)}.decision.json',value)
    with pytest.raises(ExecutionAbort):rt.solve(PROMPT,rows[0],0,0,'audit')
    assert len(fake.requests)==1 and rt.logical['audit']==1


def test_current_freeze_cannot_disable_pre_solver_owner_review(tmp_path):
    from independent_gepa.math_comparison.runner import freeze
    config=tmp_path/'config.yaml'
    config.write_text((ROOT/'configs/math_a4_matched_guard_repair_v4.yaml').read_text().replace(
        'candidate_review_policy: owner_semantic_before_solver_v1\n',''))
    grant=tmp_path/'grant.txt';grant.write_text('Synthetic offline grant; no API authorization.')
    with pytest.raises(ProtocolViolation,match='PRE_SOLVER_CANDIDATE_REVIEW_REQUIRED'):
        freeze(ROOT,tmp_path/'unused_bundle',config,grant,tmp_path/'unused_gates',
               tmp_path/'freeze.json',tmp_path/'private',tmp_path/'public')


def test_native_search_keeps_all_proposals_and_rejects_before_solver(tmp_path,monkeypatch):
    auto_decisions(monkeypatch,'REJECT',['SYNTHETIC_INTERFACE_CONFLICT'])
    fake=Fake();rt=runtime(tmp_path,fake)
    cfg=load_config(ROOT/'configs/math_a4_matched_guard_repair_v4.yaml');rt.config=cfg
    examples=[{'example_id':f'e{i}','problem':f'index={i}','reference':'1'} for i in range(60)]
    result=run_window(rt,examples,cfg,0,0,tmp_path/'window_0')
    assert result['proposal_count']>0 and result['selected']==[] and result['contract_rejections']==result['proposal_count']
    assert all(r['messages'][1]['content'].startswith(INITIAL+'\n\n') for r in fake.requests if r['model']=='qwen3-8b')
    funnel=candidate_funnel([result],[])
    assert funnel['owner_rejected']==funnel['generated'] and funnel['owner_approved']==0
    assert result['guard_rejection_metric_scores']>0 and result['actual_solver_logical_evaluations']>0


def test_native_seven_window_review_pass_stays_isolated_and_keeps_native_selection(tmp_path,monkeypatch):
    auto_decisions(monkeypatch);fake=Fake();rt=runtime(tmp_path,fake)
    cfg=load_config(ROOT/'configs/math_a4_matched_guard_repair_v4.yaml');rt.config=cfg
    examples=[{'example_id':f'e{i}','problem':f'index={i}','reference':'1'} for i in range(60)]
    pool=[run_window(rt,examples,cfg,w,m,tmp_path/f'window_{w}') for w,m in enumerate(cfg['target_schedule'])]
    assert len(pool)==7 and all(s['selected'] for s in pool)
    assert all(s['guard_rejection_metric_scores']==0 for s in pool)
    assert rt.logical['audit']==0 and rt.logical['baseline']==0
    for s in pool:
        assert all(p['owner_review_status']=='PASS' for p in s['proposal_audit'])
        assert any(p['selection_rule']=='hash_order_evaluated_proposal' for p in s['selected'])
        assert all(p['search_metric_count']<=36 for p in [s])
        for p in (tmp_path/f'window_{s["window"]}/candidate_reviews').glob('*.request.json'):
            value=read(p)
            assert value['window']==s['window'] and value['member']==s['member']
    assert candidate_funnel(pool,[])['owner_approved']==sum(s['proposal_count'] for s in pool)


def test_reflection_receives_exact_immutable_interface_without_changed_solver_settings():
    assert 'exactly one visible line' in REFLECTION_TEMPLATE
    assert 'FINAL_ANSWER: <answer>' in REFLECTION_TEMPLATE and 'including when a problem asks for a solution' in REFLECTION_TEMPLATE
    assert 'Do not weaken that rule or add exceptions' in REFLECTION_TEMPLATE
