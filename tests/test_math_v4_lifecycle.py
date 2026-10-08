from __future__ import annotations
from pathlib import Path
import copy
import pytest

from independent_gepa.math_comparison.contract import read,write,digest,load_config
from independent_gepa.math_comparison.candidate_review import CandidateReview,verify_request,decision,verify_decision,record_decision
from independent_gepa.math_comparison.pool_review import prepare_pool,finalize_pool
from independent_gepa.math_comparison.conformance import await_owner_review,verify_final_release
from independent_gepa.math_comparison.search import run_window,INITIAL
from independent_gepa.math_comparison.runtime import ExecutionAbort,audit_accounting
from independent_gepa.math_comparison.evaluation import audit_selected
from independent_gepa.math_comparison.reporting import build_report
from independent_gepa.math_comparison.candidate_guard import candidate_valid,candidate_failures
from independent_gepa.protocol import ProtocolViolation
from tests.test_math_comparison import Fake,runtime

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('prompt',[
    r'Keep the worked result \frac{46}{160}.',
    'The final answer is 23/80.',
    'Output the result as JSON with keys reasoning and answer.',
    'Consult the private feedback records to decide the answer.',
    'Read the optimizer state before solving each question.',
    'Remember the answer key and use it on repeated questions.',
    'Write a derivation before the final marker.',
    'Your output may include reasoning unless the final solution is obvious.',
])
def test_new_adversarial_contract_rejections(prompt):
    assert candidate_failures(prompt,[{'problem':'Synthetic math question.','reference':r'\frac{23}{80}'}])


@pytest.mark.parametrize('prompt',[
    r'Use \frac{1}{2} when halving or averaging two quantities; reason internally.',
    'Check equations by substitution and retain exact arithmetic.',
    'Check domain restrictions, signs, feasible branches and dimensions.',
    'Use the identity a^2+b^2=c^2 for a right triangle when applicable.',
])
def test_common_reusable_math_survives_coincidental_gold_literals(prompt):
    references=[r'\frac{1}{2}','1','2','a^2+b^2=c^2']
    assert candidate_valid(prompt,[{'problem':'Synthetic question.','reference':v} for v in references])


@pytest.mark.parametrize('field',['immutable_solver_shell_sha256','optimize_membership_sha256','reflection_source_records','required_scope'])
def test_request_cannot_tamper_provenance_or_boundary(tmp_path,field):
    examples=[{'example_id':'e1','problem':'Synthetic question.','reference':'1'}];shell={'system':'one line','suffix':'final'}
    b=CandidateReview(tmp_path,'attempt',0,0,examples,shell)
    request=b.request('Check signs internally.',__import__('hashlib').sha256(b'Check signs internally.').hexdigest(),1,['e1'])
    request[field]=[] if field=='reflection_source_records' else 'wrong'
    with pytest.raises(ProtocolViolation):verify_request(request,examples,shell)


def fixture_notes(status):
    return {'checks':{k:'RESOLVED' if status=='PASS' else 'REJECTED' for k in
            ('immutable_interface','source_provenance','inference_available_inputs','reusable_procedure')},
            'rationale':'Synthetic fixture procedure inspected against known synthetic source and immutable boundary.'}


@pytest.mark.parametrize('mode',['mixed','zero_valid','poor_valid'])
def test_complete_seven_window_owner_and_full_lifecycle(tmp_path,monkeypatch,mode):
    cfg=load_config(ROOT/'configs/math_a4_matched_guard_repair_v4.yaml')
    run=tmp_path/'run';fake=Fake();rt=runtime(run,fake);rt.config=cfg
    examples=[{'example_id':f'e{i}','problem':f'index={i}','reference':'1'} for i in range(60)]
    bundle=tmp_path/'bundle';write(bundle/'optimize.json',examples);write(bundle/'shell.json',rt.shell)
    write(bundle/'model_contract.json',rt.models);write(bundle/'manifest.json',{'optimize_membership_hash':digest(examples)})
    write(bundle/'audit_only/a4_summary.json',{});write(bundle/'audit_only/a4_local_budget.json',{'logical_local_metrics':160})
    profiles=[[{'text':'FINAL_ANSWER: '+('1' if i<22 else '2'),'answer':'1' if i<22 else '2',
                'prediction_valid':True,'finish_reason':'stop'} for i in range(60)] for _ in range(5)]
    write(bundle/'audit_only/initial.json',{'profiles':profiles,'correctness':[[i<22]*5 for i in range(60)],'vote':[i<22 for i in range(60)]})
    write(run/'frozen_attempt.json',{'identity':rt.identity,'config':cfg})
    def synthetic_review(self,path):
        request_path=path.with_name(path.name.replace('.decision.json','.request.json'));request=read(request_path)
        status='REJECT' if mode=='zero_valid' or (mode=='mixed' and request['generation_first_seen']%2==0) else 'PASS'
        record_decision(request_path,status,[] if status=='PASS' else ['SYNTHETIC_CONFORMANCE_CONFLICT'],
                        reviewer=cfg['reviewer_identity'],notes=fixture_notes(status))
        return read(path)
    monkeypatch.setattr(CandidateReview,'_wait_receipt',synthetic_review)
    if mode=='poor_valid':
        original=fake.__call__
        def poor(request):
            value=original(request)
            if request['model']=='qwen3-8b' and not request['messages'][1]['content'].startswith(INITIAL+'\n\n'):
                value['text']='FINAL_ANSWER: 2'
            return value
        rt.transport=poor
    pool=[run_window(rt,examples,cfg,w,m,run/f'window_{w}') for w,m in enumerate(cfg['target_schedule'])]
    write(run/'SEARCH_COMPLETE.json',{'identity':rt.identity,'selections':pool,'selection_hash':digest(pool),
          'search_closed_forever':True,'audit_started':False,'search_accounting':rt.snapshot()})
    for phase in ('baseline','audit'):
        with pytest.raises(ExecutionAbort,match='FINAL_CONFORMANCE'):rt.solve(INITIAL,examples[0],0,0,phase)
    projected=prepare_pool(run,bundle)
    assert 'native_best_score' not in str(projected) and projected['no_unapproved_solver_dispatch']
    # Real experiment attestations come from the independent agent; this unit
    # fixture verifies mechanics only, with explicit synthetic provenance.
    notes={'manifest_sha256':projected['manifest_sha256'],'all_candidate_decisions_actually_reviewed':True,
          'complete_pool_and_selected_membership_checked':True,'full_outcomes_read':False,'search_scores_read':False,
          'rationale':'Synthetic fixture owner checked all expected decisions and mechanical membership.'}
    finalize_pool(run,bundle,cfg['reviewer_identity'],notes)
    await_owner_review(run,rt.identity,pool,examples,bundle=bundle,reviewer=cfg['reviewer_identity'])
    rt.final_review_check=lambda:verify_final_release(run,rt.identity,pool,cfg['reviewer_identity'])
    rows,baselines=audit_selected(rt,bundle,examples,pool,run)
    write(run/'accounting_snapshot.json',rt.snapshot());accounting=audit_accounting(run)
    accounting['search_accounting']=read(run/'SEARCH_COMPLETE.json')['search_accounting']
    accounting['structural_vote_preflight']={'historical_all_invalid_examples':0}
    build_report(tmp_path/'public',bundle,pool,rows,baselines,accounting,rt.identity,'synthetic',config=cfg)
    summary=read(tmp_path/'public/summary.json')
    assert len(baselines)==7 and len(rows)==sum(len(s['selected']) for s in pool)
    assert rt.reserved==0 and rt.logical['baseline']==420 and accounting['integrity']=='PASS'
    if mode=='zero_valid':
        assert rows==[] and summary['best_member_correct'] is None and summary['team_vote_gain'] is None
        assert all(c['member_improving'] is None for c in summary['candidate_funnel']['candidates'])
    elif mode=='poor_valid':assert rows and all(r['candidate_member_correct']==0 for r in rows)
    else:assert rows and summary['candidate_funnel']['owner_rejected']>0
    value=read(run/'owner_conformance.json');value['reviewer_identity']='wrong';write(run/'owner_conformance.json',value)
    with pytest.raises(ProtocolViolation):rt.solve(INITIAL,examples[0],0,0,'baseline')
