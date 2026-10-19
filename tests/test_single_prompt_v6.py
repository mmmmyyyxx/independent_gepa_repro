"""Scientific V6 budget, native-prefix, token, content and split conformance."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from gepa import optimize
from gepa.core.adapter import EvaluationBatch
from gepa.utils import MaxCandidateProposalsStopper
from independent_gepa.protocol import ProtocolViolation
from independent_gepa.single_prompt_math.budget import NativeBudget
from independent_gepa.single_prompt_math.common import Abort,read,write,digest,file_hash
from independent_gepa.single_prompt_math.runner import load_config
from independent_gepa.single_prompt_math.runtime import Runtime
from independent_gepa.single_prompt_math.prompt import SystemPrompt
from independent_gepa.single_prompt_math.search import run_repeat
from independent_gepa.single_prompt_math.tokens import TokenLedger
from independent_gepa.single_prompt_math.telemetry import native_value_at,token_value_at
from independent_gepa.single_prompt_math import posthoc,heldout
from independent_gepa.single_prompt_math.analysis import paired,align_tokens
from tests.test_single_prompt_math import models,initial,rows,response,Fake,fixture_bundle

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def config():return load_config(ROOT)


@pytest.mark.parametrize('limit,size,allowed',[(100,100,True),(100,101,False),(206,106,True),(205,206,False)])
def test_atomic_entire_batch_admission(limit,size,allowed):
    b=NativeBudget(limit,100,3,1000)
    if allowed:
        b.admit(size,'synthetic');assert b.used==size
    else:
        with pytest.raises(Abort,match='BATCH_BUDGET'):b.admit(size,'synthetic')
        assert b.used==0 and b.batches==[]


@pytest.mark.parametrize('used,expected,reason',[(100,False,None),(194,False,None),(195,True,'insufficient_complete_iteration_budget'),(300,True,'budget_exhausted')])
def test_complete_iteration_reserve_boundary(used,expected,reason):
    b=NativeBudget(300,100,3,1000);b.admit(used,'fixture')
    assert b(SimpleNamespace(total_num_evals=used,i=0)) is expected
    assert b.reason==reason


def test_unexpected_insufficient_full_batch_is_failure_not_a_wrong_score():
    b=NativeBudget(205,100,3,1000);b.admit(100,'seed')
    assert b(SimpleNamespace(total_num_evals=100,i=-1))
    # Defensive batch admission still fails closed if an invariant is bypassed.
    b.admit(6,'unexpected_partial_iteration')
    with pytest.raises(Abort,match='BATCH_BUDGET'):b.admit(100,'full')
    assert b.used==106


@pytest.mark.parametrize('selector',['current_best','pareto'])
def test_budget_wrapper_preserves_native_prefix_when_cap_does_not_bind(tmp_path,selector):
    class Adapter:
        def __init__(self,budget):self.budget=budget;self.count=0;self.generation=0
        def evaluate(self,batch,candidate,capture_traces=False):
            if self.budget:self.budget.admit(len(batch),'fixture')
            self.count+=len(batch)
            changed=candidate['role']!='base'
            values=[float(changed and (capture_traces is False)) for _ in batch]
            return EvaluationBatch(outputs=[None]*len(batch),scores=values,trajectories=[{} for _ in batch] if capture_traces else None)
        def make_reflective_dataset(self,candidate,eval_batch,components_to_update):return {c:[{'feedback':'fixture'}] for c in components_to_update}
        def propose_new_texts(self,candidate,reflective_dataset,components_to_update):
            self.generation+=1;return {'role':'candidate_'+str(self.generation)}
    results=[]
    for wrapped in (False,True):
        budget=NativeBudget(10000,4,3,25) if wrapped else None
        adapter=Adapter(budget)
        result=optimize(seed_candidate={'role':'base'},trainset=[0,1,2],valset=[0,1,2,3],adapter=adapter,
            candidate_selection_strategy=selector,reflection_minibatch_size=3,frontier_type='instance',
            module_selector='round_robin',skip_perfect_score=True,use_merge=False,cache_evaluation=False,
            val_evaluation_policy='full_eval',stop_callbacks=budget if wrapped else MaxCandidateProposalsStopper(25),
            seed=42,run_dir=str(tmp_path/str(wrapped)),display_progress_bar=False)
        results.append(result.to_dict())
        assert result.total_metric_calls==adapter.count
    for key in ('candidates','parents','val_aggregate_scores','val_subscores','discovery_eval_counts','total_metric_calls'):
        assert results[0][key]==results[1][key]


@pytest.mark.parametrize('mode',['perfect','no_local_gain'])
def test_more_than_twenty_opportunities_and_no_candidate_paths(tmp_path,config,models,initial,mode):
    def transport(role,request):
        if role=='reflection':return response('```\nCheck arithmetic carefully.\n```')
        return response('Final answer:'+('1' if mode=='perfect' else '0'))
    cfg={**config,'native_logical_budget':300,'max_native_proposals':1000}
    rt=Runtime(tmp_path,cfg,models,'fake',transport);rt.bind_arm('strict_validation')
    result=run_repeat(rt,cfg,initial,rows('optimize',6),rows('validation',4),tmp_path/'cell',1)
    assert result['native_iterations']>20 and result['native_metric_calls']<=300
    assert result['native_budget']['remaining']<10
    assert result['native_accepted']==0
    if mode=='perfect':assert result['generated']==0


def test_impossible_initial_native_budget_dispatches_nothing(tmp_path,config,models,initial):
    fake=Fake();rt=Runtime(tmp_path,config,models,'fake',fake);rt.bind_arm('strict_validation')
    cfg={**config,'native_logical_budget':3}
    with pytest.raises(Abort,match='INITIAL_VALIDATION'):
        run_repeat(rt,cfg,initial,rows('optimize',6),rows('validation',4),tmp_path/'cell',1)
    assert fake.calls==[]


def test_native_3000_call_bound_with_repeated_full_batches(tmp_path):
    budget=NativeBudget(3000,100,3,1000)
    class Adapter:
        def __init__(self):self.generation=0
        def evaluate(self,batch,candidate,capture_traces=False):
            budget.admit(len(batch),'synthetic')
            value=float(candidate['role']!='base' and not capture_traces)
            return EvaluationBatch(outputs=[None]*len(batch),scores=[value]*len(batch),trajectories=[{} for _ in batch] if capture_traces else None)
        def make_reflective_dataset(self,candidate,eval_batch,components_to_update):return {c:[{'feedback':'fixture'}] for c in components_to_update}
        def propose_new_texts(self,candidate,reflective_dataset,components_to_update):
            self.generation+=1;return {'role':str(self.generation)}
    result=optimize(seed_candidate={'role':'base'},trainset=list(range(3)),valset=list(range(100)),adapter=Adapter(),
        candidate_selection_strategy='pareto',reflection_minibatch_size=3,use_merge=False,cache_evaluation=False,
        val_evaluation_policy='full_eval',stop_callbacks=budget,seed=42,run_dir=str(tmp_path),display_progress_bar=False)
    assert result.total_metric_calls==budget.used==2962
    assert budget.limit-budget.used==38 and budget.reason=='insufficient_complete_iteration_budget'


def test_shared_observation_attribution_has_no_second_arm_free_advantage(tmp_path,config,models,initial):
    rt=Runtime(tmp_path,config,models,'fake',lambda *a:response('Final answer:1'))
    prompt=SystemPrompt.from_dict(initial);row=rows('optimize',1)[0]
    for arm in config['arms']:
        rt.bind_arm(arm);rt.register_prompt(prompt,1)
        rt.prediction(prompt,row,1,'optimize');rt.prediction(prompt,row,1,'optimize')
    left=rt.tokens.view('search','strict_validation',1);right=rt.tokens.view('search','native_pareto',1)
    assert left['actual_dispatch']['accounted_tokens']==14 and right['actual_dispatch']['accounted_tokens']==0
    assert left['standalone_attributed']==right['standalone_attributed']
    assert left['standalone_attributed']['accounted_tokens']==14
    assert TokenLedger.replay(tmp_path).view()==rt.tokens.view()


def test_diagnostic_token_components_are_separate_from_native_and_test(tmp_path,config,models,initial):
    rt=Runtime(tmp_path,config,models,'fake',lambda *a:response('Final answer:1'))
    rt.bind_arm('strict_validation');p=SystemPrompt.from_dict(initial);rt.register_prompt(p,1)
    data=rows('optimize',3)
    for row,kind in zip(data,['initial_diagnostic','native','selected_diagnostic']):rt.prediction(p,row,1,'optimize',kind)
    pieces=rt.tokens.view('search','strict_validation',1)['actual_dispatch']['components']
    assert {k:v['accounted_tokens'] for k,v in pieces.items()}=={'initial_diagnostic':14,'native':14,'selected_diagnostic':14}


def test_failed_request_bounds_and_success_tokens_are_separate(tmp_path,config,models,initial,monkeypatch):
    import httpx
    from openai import APIConnectionError
    attempts=[]
    def transport(*args):
        attempts.append(True)
        if len(attempts)==1:raise APIConnectionError(request=httpx.Request('POST','https://fixture.invalid'))
        return response('Final answer:1')
    rt=Runtime(tmp_path,config,models,'fake',transport);rt.bind_arm('strict_validation')
    monkeypatch.setattr(rt,'wait_provider',lambda role:None)
    # Cooldown is consumed by wait_provider in production; isolate deterministic retry here.
    monkeypatch.setattr(rt,'guard',lambda:rt.provider_cooldowns.clear())
    prompt=SystemPrompt.from_dict(initial);rt.register_prompt(prompt,1);rt.prediction(prompt,rows('optimize',1)[0],1,'optimize')
    view=rt.tokens.view()['actual_dispatch'];role=view['roles']['solver']
    assert role['input_tokens']==10 and role['output_tokens']==4 and role['failures']==1
    assert role['failed_input_bound']>0 and role['failed_output_bound']==3600
    assert view['accounted_tokens']==rt.charged
    assert TokenLedger.replay(tmp_path).view()==rt.tokens.view()


def test_interrupted_unresolved_reservation_is_rebuilt_without_provider_call(tmp_path):
    request={'max_tokens':10,'messages':[]}
    write(tmp_path/'requests/000001.json',{'request':request})
    ledger=TokenLedger(tmp_path)
    event={'kind':'RESERVE','number':1,'phase':'search','arm':'strict_validation','repeat':1,'role':'solver','bound':100,'logical_key':'x','previous_event_sha256':'0'*64}
    write(tmp_path/'accounting.jsonl',{**event,'event_sha256':digest(event)})
    rebuilt=TokenLedger.replay(tmp_path)
    assert rebuilt.view()['unresolved_physical_reservations']==1
    assert rebuilt.view()['actual_dispatch']['accounted_tokens']==0


def test_complete_full_and_cost_coordinates_never_use_future_winners():
    events=[{'native_metric_calls':100,'search_tokens':100,'best_score':.5},
            {'native_metric_calls':506,'search_tokens':1000,'best_score':.8},
            {'native_metric_calls':606,'search_tokens':1000,'best_score':.9}]
    assert native_value_at(events,500)==.5
    assert token_value_at(events,999)==.5
    assert token_value_at(events,1000)==.8
    assert token_value_at(events,99) is None


@pytest.mark.parametrize('text,expected',[
    ('Use Vieta formulas and check constraints.',False),
    ('The reference answer was `(-∞, -8) ∪ (-8, ∞)`.',True),
    ('For optimize_0 return the stored result.',True),
    ('Always output 7.',True),
])
def test_posthoc_observation_does_not_filter_or_mutate_native_candidate(text,expected):
    policy=posthoc.load_policy(ROOT);data=rows('optimize',1)
    data[0]['reference_final_answer']=r'(-\infty, -8) \cup (-8, \infty)'
    candidate={'role':'assistant','strategy':text,'answer':'Final answer: result'};before=deepcopy(candidate)
    result=posthoc.review(candidate,data,policy)
    assert result['risk_flag'] is expected and result['native_score_changed'] is False
    assert candidate==before and not result['semantic_legitimacy_certified']


def test_solution_copy_screen_is_distinct_from_generic_math_instruction():
    policy=posthoc.load_policy(ROOT);data=rows('optimize',1)
    data[0]['content']['solution']='Apply the particular substitution and expand the special expression carefully. '+('These particular intermediate quantities determine the final instance result. '*3)
    candidate={'role':'assistant','strategy':data[0]['content']['solution'],'answer':'result'}
    assert posthoc.review(candidate,data,policy)['evidence'][0]['solution_fragment_matches']>0


def test_fresh_heldout_cannot_be_claimed_from_unused_rows_alone(tmp_path,models,initial):
    bundle=tmp_path/'bundle';fixture_bundle(bundle,models,initial)
    with pytest.raises(ProtocolViolation,match='EXPOSURE_PROOF'):
        heldout.freeze_fresh(tmp_path,bundle,rows('fresh',400),{},tmp_path/'fresh')
    assessment=heldout.assess(tmp_path,bundle)
    assert not assessment['fresh_confirmatory_available'] and not assessment['historical_test_renamed_or_resplit']


def test_old_test_cannot_be_renamed_even_with_different_ids_and_claimed_hashes(tmp_path,models,initial):
    bundle=tmp_path/'bundle';fixture_bundle(bundle,models,initial);proof=tmp_path/'proof.txt';proof.write_text('synthetic proof')
    exposure={'identity':'REVIEWED_COMPLETE_EXPOSURE_INVENTORY_V1','owner_reviewed_complete':True,
        'scopes':sorted(heldout.REQUIRED_SCOPES),'files':{'proof.txt':file_hash(proof)}}
    renamed=read(bundle/'test.json')
    for i,row in enumerate(renamed):row.update(stable_example_id='renamed_'+str(i),input_sha256='fake_'+str(i))
    with pytest.raises(ProtocolViolation,match='INSUFFICIENT_UNEXPOSED'):
        heldout.freeze_fresh(tmp_path,bundle,renamed,exposure,tmp_path/'fresh')


@pytest.mark.parametrize('phase,split',[('search','optimize'),('search','validation'),('test','test')])
def test_same_v5_repair_is_bound_to_every_runtime_phase_and_audit(tmp_path,config,models,initial,phase,split):
    from independent_gepa.single_prompt_math import runtime,audit,scoring
    assert runtime.score is audit.score is scoring.score
    assert config['local_timeout_attempts_at_ceiling']==2
    rt=Runtime(tmp_path,config,models,'fake',lambda *a:response(r'Final answer:(2+\sqrt{2})^{3^{77}-1}'))
    rt.phase=phase;rt.test_release_check=lambda:None;rt.bind_arm('strict_validation')
    prompt=SystemPrompt.from_dict(initial);rt.register_prompt(prompt,1)
    result=rt.prediction(prompt,rows(split,1)[0],1,split)
    assert result['valid'] and result['correct'] is False
    assert rt.roles['solver']['successes']==1


def test_reviewed_fresh_contract_is_distinct_frozen_and_tamper_checked(tmp_path,models,initial):
    bundle=tmp_path/'bundle';fixture_bundle(bundle,models,initial);proof=tmp_path/'proof.txt';proof.write_text('synthetic complete exposure proof')
    exposure={'identity':'REVIEWED_COMPLETE_EXPOSURE_INVENTORY_V1','owner_reviewed_complete':True,
        'scopes':sorted(heldout.REQUIRED_SCOPES),'files':{'proof.txt':file_hash(proof)},'stable_ids':[],'input_hashes':[]}
    artifact=tmp_path/'fresh';manifest=heldout.freeze_fresh(tmp_path,bundle,rows('fresh',400),exposure,artifact)
    spec=heldout.contract(bundle,artifact);assert spec['mode']=='reviewed_fresh_heldout'
    assert len(heldout.load_test(bundle,spec))==300
    assert manifest['membership_hash']!=heldout.contract(bundle)['membership_hash']
    (artifact/'test.json').write_text('[]\n')
    with pytest.raises(ProtocolViolation,match='HASH_CHANGED'):heldout.load_test(bundle,spec)


def test_paired_item_changes_and_two_way_bootstrap_preserve_pairing():
    profiles={}
    for repeat in (1,2,3):
        profiles[('strict_validation',repeat)]=[{'example_id':str(i),'correct':i==0} for i in range(3)]
        profiles[('native_pareto',repeat)]=[{'example_id':str(i),'correct':i==1} for i in range(3)]
    result=paired(profiles,bootstrap_draws=100)
    assert result['mean_difference']==0 and result['ties']==3
    assert all(r['corrected']==r['regressed']==1 for r in result['per_repeat'])
    profiles[('native_pareto',2)][0]['example_id']='wrong'
    with pytest.raises(ProtocolViolation,match='MEMBERSHIP'):paired(profiles,100)


def test_production_default_is_3000_and_old_config_remains_historical(config):
    assert config['native_logical_budget']==3000 and config['max_native_proposals']>966
    assert 'max_native_iterations' not in config
    assert 'max_native_iterations: 20' in (ROOT/'configs/gepa_single_prompt_math_seed42_repeat3.yaml').read_text(encoding='utf-8')
