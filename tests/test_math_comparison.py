from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import socket

import pytest

from independent_gepa.math_comparison import benchmark
from independent_gepa.math_comparison.contract import PINS,SETTINGS,digest,load_config,read,write
from independent_gepa.math_comparison.evaluation import audit_selected
from independent_gepa.math_comparison.runtime import Runtime,ExecutionAbort,audit_accounting
from independent_gepa.math_comparison.search import MathAdapter,INITIAL,run_window,prompt_hash
from independent_gepa.math_comparison.reporting import build_report
from independent_gepa.protocol import ProtocolViolation

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args,**kwargs): raise AssertionError('OFFLINE_NETWORK_FORBIDDEN')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(socket,'create_connection',forbidden)

def models():
    return {'models':{'solver':'qwen3-8b','optimizer_reflection':'qwen3.7-flash','solver_thinking':False},
        'solver_decoding_policy':{'identity':'SOLVER_DECODING_POLICY_V2','enable_thinking':False,
            'frequency_penalty':0,'max_output_tokens':3600,'min_p':0,'presence_penalty':0,'temperature':0.2,'top_k':20,'top_p':0.8},
        'optimizer_generation_policy':{'identity':'OPTIMIZER_REFLECTION_GENERATION_POLICY_V3',
            'model':'qwen3.7-flash','enable_thinking':False,'frequency_penalty':0,'presence_penalty':1.5,
            'temperature':0.7,'top_k':20,'top_p':0.8,'max_completion_tokens':1800,'accounting_output_ceiling':1810},
        'decoding':{'timeout_seconds':120,'transport_retries':20},'evaluator_pins':PINS,
        'invalid_recovery_policy':{'max_semantic_attempts':4},
        'prediction_validity_policy':{'identity':'MATH_PREDICTION_VALIDITY_V2'}}

class Fake:
    def __init__(self): self.reflections=0; self.requests=[]
    def __call__(self,request):
        self.requests.append(copy.deepcopy(request))
        if request['model']=='qwen3.7-flash':
            self.reflections+=1
            text=f'```\nUse reusable algebraic reasoning and check the derivation. Revision {chr(65+self.reflections)}.\n```'
        else:
            content=request['messages'][1]['content']; index=int(re.search(r'index=(\d+)',content)[1])
            good=index<22 or (not content.startswith(INITIAL+'\n\n') and index<40)
            text='FINAL_ANSWER: '+('1' if good else '2')
        return {'text':text,'finish_reason':'stop','input_tokens':20,'output_tokens':10,
                'reasoning_tokens':None,'reasoning_character_count':0}

def runtime(tmp_path,transport):
    tmp_path.mkdir(parents=True,exist_ok=True)
    return Runtime(tmp_path,load_config(ROOT/'configs/math_a4_matched.yaml'),models(),
                   {'system':'immutable formatting','suffix':'\nformat suffix'},'synthetic-attempt',transport)

@pytest.mark.parametrize('text,finish,reason',[
    ('','stop','MISSING_FINAL_MARKER'),('FINAL_ANSWER:','stop','EMPTY_FINAL_PAYLOAD'),
    ('FINAL_ANSWER: 1\nFINAL_ANSWER: 1','stop','MULTIPLE_FINAL_MARKERS'),
    ('FINAL_ANSWER: 1\ncommentary','stop','OTHER_PREDICTION_CONTRACT_FAILURE'),
    ('FINAL_ANSWER: 1','length','OUTPUT_TRUNCATED'),('FINAL_ANSWER: 1','bad','OTHER_PREDICTION_CONTRACT_FAILURE'),
    ('Reasoning\nFINAL_ANSWER: 1','stop',None),('FINAL_ANSWER: (1,2)','stop','PAYLOAD_UNSUPPORTED')])
def test_strict_framing_and_native_payload(text,finish,reason):
    assert benchmark.classify(text,finish)['invalid_reason']==reason

def test_gold_first_math_and_container_boundary():
    assert benchmark.correct(benchmark.classify('FINAL_ANSWER: \\frac{1}{2}'),'0.5')
    assert not benchmark.correct(benchmark.classify('FINAL_ANSWER: x=1'),'1')
    with pytest.raises(ProtocolViolation): benchmark.require_reference('(1,2)')

def test_exact_solver_and_reflection_wire_and_namespace(tmp_path):
    fake=Fake();rt=runtime(tmp_path,fake);example={'problem':'index=0','reference':'1'}
    rt.solve(INITIAL,example,0,0,'search');rt.solve(INITIAL,example,0,0,'audit')
    assert rt.physical==1 and rt.cache_hits==1 and rt.logical['audit']==1
    rt.solve(INITIAL,example,0,1,'search');rt.solve(INITIAL,example,1,0,'search')
    assert rt.physical==3
    req=fake.requests[0]
    assert req=={'model':'qwen3-8b','messages':[{'role':'system','content':'immutable formatting'},
        {'role':'user','content':INITIAL+'\n\nindex=0\nformat suffix'}],
        'enable_thinking':False,'frequency_penalty':0,'max_tokens':3600,'min_p':0,'presence_penalty':0,
        'temperature':0.2,'top_k':20,'top_p':0.8}
    rt.reflect('native instruction',0);req=fake.requests[-1]
    assert req['max_completion_tokens']==1800 and 'max_tokens' not in req and req['presence_penalty']==1.5
    assert req['enable_thinking'] is False and req['temperature']==0.7
    write(tmp_path/'accounting_snapshot.json',rt.snapshot());assert audit_accounting(tmp_path)['charged_tokens']==120

def test_first_valid_wrong_stops_and_terminal_requires_four(tmp_path):
    responses=iter(['bad','FINAL_ANSWER: 2','FINAL_ANSWER: 1'])
    def transport(request): return {'text':next(responses),'finish_reason':'stop','input_tokens':1,'output_tokens':1}
    rt=runtime(tmp_path/'resolved',transport);row=rt.solve(INITIAL,{'problem':'index=0','reference':'1'},0,0,'search')
    assert row['semantic_attempt_count']==2 and row['prediction_valid'] and not row['correct'] and rt.physical==2
    rt=runtime(tmp_path/'terminal',lambda r:{'text':'bad','finish_reason':'stop','input_tokens':1,'output_tokens':1})
    row=rt.solve(INITIAL,{'problem':'index=0','reference':'1'},0,0,'search')
    assert row['semantic_attempt_count']==4 and row['terminal_invalid'] and rt.physical==4

def test_resource_admission_and_unknown_usage_are_fail_closed(tmp_path):
    fake=Fake();rt=runtime(tmp_path/'ceiling',fake);rt.charged=2_999_999
    with pytest.raises(ExecutionAbort): rt.solve(INITIAL,{'problem':'index=0','reference':'1'},0,0,'search')
    assert not fake.requests
    rt=runtime(tmp_path/'unknown',lambda r:{'text':'FINAL_ANSWER: 1','finish_reason':'stop'})
    with pytest.raises(ExecutionAbort): rt.solve(INITIAL,{'problem':'index=0','reference':'1'},0,0,'search')
    assert rt.charged>0 and rt.reserved==0

def test_feedback_and_support_are_individual_optimize_only(tmp_path):
    rt=runtime(tmp_path,Fake());example={'example_id':'a','problem':'index=0','reference':'1'}
    adapter=MathAdapter(rt,[example],0,0,tmp_path)
    result=adapter.evaluate([example],{'system_prompt':INITIAL},True)
    feedback=adapter.make_reflective_dataset({'system_prompt':INITIAL},result,['system_prompt'])
    assert set(feedback['system_prompt'][0])=={'Problem','Current Member Response','Parsed Answer','Gold Answer','Correct','Valid','Failure Reason'}
    with pytest.raises(ProtocolViolation): adapter.evaluate([{'example_id':'heldout','problem':'index=1','reference':'1'}],{'system_prompt':INITIAL})
    with pytest.raises(ProtocolViolation): rt.solve(INITIAL,example,0,0,'validation')
    with pytest.raises(ProtocolViolation): adapter.evaluate([example],{'peer_prompt':'secret'})

def test_seven_native_windows_then_full_audit_include_rejected_candidates(tmp_path):
    fake=Fake();private=tmp_path/'private';rt=runtime(private,fake)
    examples=[{'example_id':f'e{i}','problem':f'index={i}','reference':'1'} for i in range(60)]
    config=load_config(ROOT/'configs/math_a4_matched.yaml');selections=[]
    for window,member in enumerate(config['target_schedule']):
        result=run_window(rt,examples,config,window,member,private/f'window_{window}');selections.append(result)
        assert result['search_metric_count']<=36 and result['proposal_count']<=6
        assert result['selected'] and len(result['selected'])<=4
        assert any(r['selection_rule']=='hash_order_evaluated_proposal' for r in result['selected'])
        events=[json.loads(line) for line in (private/f'window_{window}/history.jsonl').read_text().splitlines()]
        assert any(e['kind']=='rejected' for e in events)
    assert rt.logical['audit']==0 and rt.logical['baseline']==0
    bundle=tmp_path/'bundle'
    profiles=[[{'text':'FINAL_ANSWER: '+('1' if i<22 else '2'),'answer':'1' if i<22 else '2',
                'prediction_valid':True,'finish_reason':'stop'} for i in range(60)] for _ in range(5)]
    write(bundle/'audit_only/initial.json',{'profiles':profiles,'correctness':[[i<22]*5 for i in range(60)],
        'vote':[i<22 for i in range(60)]})
    with pytest.raises(ProtocolViolation): audit_selected(rt,bundle,examples,selections,private)
    write(private/'SEARCH_COMPLETE.json',{'selection_hash':digest(selections)})
    selected_before=digest(selections);rows,baselines=audit_selected(rt,bundle,examples,selections,private)
    assert digest(selections)==selected_before and len(rows)>=7
    assert all(r['candidate_member_correct']==40 and r['original_correct_lost']==0 and r['v22_admissible'] for r in rows)
    assert all(r['team_vote_delta']==0 and r['oracle_delta']==18 for r in rows)
    assert all(b['fresh_initial_correct']==22 for b in baselines)
    write(private/'accounting_snapshot.json',rt.snapshot());assert audit_accounting(private)['integrity']=='PASS'
    write(bundle/'manifest.json',{'optimize_membership_hash':digest([r['example_id'] for r in examples])})
    write(bundle/'audit_only/a4_summary.json',{})
    write(bundle/'audit_only/a4_local_budget.json',{'logical_local_metrics':160})
    accounting=audit_accounting(private)
    accounting['search_accounting']={'charged_tokens':100}
    accounting['structural_vote_preflight']={'historical_all_invalid_examples':0}
    build_report(tmp_path/'public',bundle,selections,rows,baselines,accounting,'f'*64,'e'*40)
    assert read(tmp_path/'public/summary.json')['integrity']=='VALID'

def test_config_does_not_unlock_heldout_or_extra_budget(tmp_path):
    text=(ROOT/'configs/math_a4_matched.yaml').read_text().replace('token_ceiling: 3000000','token_ceiling: 3000001')
    path=tmp_path/'bad.yaml';path.write_text(text)
    with pytest.raises(ProtocolViolation): load_config(path)
