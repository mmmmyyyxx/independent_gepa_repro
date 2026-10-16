"""Selector semantics and complete paired lifecycle using synthetic providers only."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from independent_gepa.protocol import ProtocolViolation
from independent_gepa.single_prompt_math.common import Abort,digest,read,write,file_hash
from independent_gepa.single_prompt_math.bundle import FILES,load_rows
from independent_gepa.single_prompt_math.prompt import SystemPrompt
from independent_gepa.single_prompt_math.runtime import Runtime
from independent_gepa.single_prompt_math.runner import load_config,execute,publish,build_summary
from independent_gepa.single_prompt_math.search import run_repeat
from independent_gepa.single_prompt_math.audit import reconcile
from independent_gepa.single_prompt_math.math_flexible_answer import classify_prediction

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def config():return load_config(ROOT)


@pytest.fixture(scope='module')
def models():
    return {'routes':{
        'solver':{'model':'gpt-4o-mini','provider_profile':'openlux','api_key_env':'OPENLUX_API_KEY','base_url_env':'OPENLUX_BASE_URL'},
        'reflection':{'model':'qwen3.7-flash','provider_profile':'lwj','api_key_env':'LWJ_DASHSCOPE_API_KEY','base_url_env':'LWJ_DASHSCOPE_BASE_URL'}},
        'solver_decoding_policy':{'temperature':0.2,'top_p':0.8,'presence_penalty':0,'frequency_penalty':0},
        'optimizer_generation_policy':{'temperature':0.7,'top_p':0.8,'presence_penalty':1.5,'frequency_penalty':0,
            'max_completion_tokens':1800,'top_k':20},'first_solver_capacity':3600,'length_recovery_capacity':6144,
        'provider_timeout_seconds':120,'optimizer_input_limit':991808,'optimizer_context_limit':1000000}


@pytest.fixture(scope='module')
def initial():return {'role':'You solve mathematical tasks.','strategy':'Compute the requested quantity.','answer':'Declare the final answer explicitly.'}


@pytest.fixture(scope='module')
def frozen_reference(tmp_path_factory):
    """Read the registered Git identity, independently of a changing sibling worktree."""
    import io
    import zipfile
    source=ROOT.parent/'multi_agent_diversity'
    if not source.exists():pytest.skip('optional sibling parity source is unavailable')
    provenance=read(ROOT/'experiments/protocols/gepa_single_prompt_math_seed42_repeat3_v4/copied_scoring_sources.json')
    snapshot=tmp_path_factory.mktemp('frozen_reference')
    archive=subprocess.check_output(['git','archive','--format=zip',provenance['reference_source_sha'],
                                     'multi_dataset_diverse_rl'],cwd=source)
    with zipfile.ZipFile(io.BytesIO(archive)) as package:
        assert all((snapshot/name).resolve().is_relative_to(snapshot.resolve()) for name in package.namelist())
        package.extractall(snapshot)
    for record in provenance['copied']:
        path=snapshot/record['source']
        # Git archive applies export attributes; parity requires the raw Git blob.
        path.write_bytes(subprocess.check_output(['git','show',provenance['reference_source_sha']+':'+record['source']],cwd=source))
        if file_hash(path)!=record['source_file_sha256']:
            # The registered prompt file was exported from a CRLF working copy.
            # Restore only that line ending convention; retain the exact hash check.
            path.write_bytes(path.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))
        assert file_hash(path)==record['source_file_sha256']
    worker='multi_dataset_diverse_rl/benchmarks/math_domain_worker.py'
    (snapshot/worker).write_bytes(subprocess.check_output(['git','show',provenance['reference_source_sha']+':'+worker],cwd=source))
    return snapshot


def rows(split,count):
    return [{'stable_example_id':f'{split}_{i}','content':{'problem':f'Synthetic {split} item {i}.',
        'solution':'A deterministic fixture solution used solely for offline verification.'},
        'reference_final_answer':'1'} for i in range(count)]


def response(text,finish='stop'):
    return {'text':text,'finish_reason':finish,'input_tokens':10,'output_tokens':4,
            'reasoning_tokens':0,'reasoning_character_count':0,
            'provider_usage_details':{'completion_tokens_details':{'reasoning_tokens':0}},
            'provider_reasoning_character_count':0,'provider_reasoning_content_present':False,
            'provider_response_accepted':True,'provider_metadata_loss_audited':True}


class Fake:
    def __init__(self,mode='mixed'):self.mode=mode;self.calls=[]
    def __call__(self,role,request):
        self.calls.append((role,deepcopy(request)))
        if role=='reflection':
            text='Always output 7.' if self.mode=='fixed_payload' else 'Check intermediate arithmetic carefully.'
            return response('```\n'+text+'\n```')
        changed='carefully' in request['messages'][0]['content'].lower()
        if self.mode=='no_local_gain':correct=changed and 'validation' in request['messages'][1]['content']
        elif self.mode=='val_tie':correct=changed and 'optimize' in request['messages'][1]['content']
        else:correct=changed and self.mode=='mixed'
        return response('Working is permitted.\nFinal answer: '+('1' if correct else '0'))


def fixture_bundle(path,models,initial):
    path.mkdir();counts={'optimize':150,'validation':100,'test':300}
    write(path/'initial.json',initial);write(path/'model_contract.json',models);write(path/'reference.json',{'fake_only':True})
    membership={}
    for split,n in counts.items():
        data=rows(split,n);write(path/f'{split}.json',data);membership[split]=digest([r['stable_example_id'] for r in data])
    manifest={'identity':'SINGLE_PROMPT_MATH_COMPARISON_BUNDLE_V1','counts':counts,'membership_hashes':membership,
              'files':{f:file_hash(path/f) for f in FILES}}
    manifest['bundle_hash']=digest(manifest);write(path/'manifest.json',manifest)
    return manifest


@pytest.fixture(scope='module',params=['mixed','fixed_payload','recovering'])
def complete_fake(request,tmp_path_factory,config,models,initial):
    tmp_path=tmp_path_factory.mktemp('gepa_two_arm_'+request.param)
    monkeypatch=pytest.MonkeyPatch()
    # Warm only the numeric fixtures, avoiding an artificial cold-start stampede
    # from an instant fake transport under production Solver32 concurrency.
    from independent_gepa.single_prompt_math.math_domain_v2 import score
    for answer in ('0','1'):score(classify_prediction('Final answer: '+answer),'1')
    bundle=tmp_path/'bundle';manifest=fixture_bundle(bundle,models,initial)
    frozen={'config':config,'bundle_hash':manifest['bundle_hash'],'fake_only_fixture':True}
    frozen['identity']=digest(frozen);freeze=tmp_path/'freeze.json';write(freeze,frozen)
    fake=Fake('mixed' if request.param=='recovering' else request.param);captured=[]
    transport=fake
    if request.param=='recovering':
        import threading,httpx
        from openai import APIStatusError,APIConnectionError
        fault_lock=threading.Lock();failed_roles=set()
        def transport(role,request):
            with fault_lock:
                fail=role not in failed_roles
                failed_roles.add(role)
            if fail:
                wire=httpx.Request('POST','https://fixture.invalid/v1')
                if role=='solver':raise APIStatusError('fixture unavailable',response=httpx.Response(503,request=wire),body={})
                raise APIConnectionError(request=wire)
            return fake(role,request)
    import independent_gepa.single_prompt_math.search as search
    real_optimize=search.optimize
    def observed(**kwargs):
        common={k:v for k,v in kwargs.items() if k not in
                ('adapter','reflection_lm','run_dir','logger','callbacks','trainset','valset','stop_callbacks')}
        common['stop_max_proposals']=kwargs['stop_callbacks'].max_proposals
        captured.append(common);return real_optimize(**kwargs)
    monkeypatch.setattr(search,'optimize',observed)
    run=tmp_path/'run';result=execute(ROOT,bundle,freeze,run,transport_override=transport)
    yield SimpleNamespace(run=run,bundle=bundle,result=result,fake=fake,mode=request.param,captured=captured)
    monkeypatch.undo()


def test_complete_six_cell_pipeline_and_paired_realizations(complete_fake):
    f=complete_fake;r=f.result
    assert r['status']=='EXECUTION_COMPLETE' and r['fake_provider']
    assert len(r['selections'])==len(r['test_results'])==6
    assert all(s['seed']==42 and s['native_iterations']==20 for s in r['selections'])
    assert {s['arm'] for s in r['selections']}=={'strict_validation','native_pareto'}
    assert r['accounting']['pending_physical_attempts']==0
    assert all(s['generated']>0 for s in r['selections']), 'silent proposer failures must not pass'
    assert read(f.run/'search_audit.json')['status']=='PASS'
    assert read(f.run/'final_audit.json')['status']=='PASS'
    assert read(f.run/'SEARCH_COMPLETE.json')['test_opened'] is False
    assert r['accounting']['cache_hits']>=900
    summary=build_summary(r,read(f.run/'frozen.json'),read(f.run/'final_audit.json'))
    assert summary['status']=='FAKE_ENGINEERING_FIXTURE'
    assert summary['pareto_win_tie_loss']=={'wins':0,'ties':3,'losses':0}
    assert all(s['test_sample_standard_deviation']==0 for s in summary['per_arm'].values())
    if f.mode!='fixed_payload':assert all(t['correct']==300 for t in r['test_results'])
    else:
        assert all(s['native_parseable']==s['generated'] and s['guard_zero_metrics']==0 for s in r['selections'])
        assert all(t['correct']==0 for t in r['test_results'])
    if f.mode=='recovering':
        assert r['accounting']['transient_failure_attempts_by_category']=={'HTTP_503':1,'CONNECTION_FAILURE':1}
        assert r['accounting']['roles']['solver']['network_failed_attempts']==1
        assert r['accounting']['roles']['reflection']['network_failed_attempts']==1
    for repeat in (1,2,3):
        a=read(f.run/f'strict_validation/repeat_{repeat}/initial_optimize.json')
        b=read(f.run/f'native_pareto/repeat_{repeat}/initial_optimize.json')
        assert a==b
    left=f.captured[0];right=f.captured[3]
    assert {k for k in left if left[k]!=right[k]}=={'candidate_selection_strategy'}
    assert left['candidate_selection_strategy']=='current_best' and right['candidate_selection_strategy']=='pareto'
    assert 'batch_sampler' not in left and left['reflection_minibatch_size']==3
    with pytest.raises(ProtocolViolation,match='REAL_COMPLETE'):publish(ROOT,f.run,f.run/'public')


def test_wire_tamper_detected_independently(complete_fake):
    f=complete_fake;path=next((f.run/'requests').glob('*.json'));original=read(path);value=deepcopy(original)
    value['request']['temperature']=0.99;write(path,value)
    try:
        with pytest.raises(ProtocolViolation,match='WIRE'):reconcile(f.run,f.bundle,include_test=True)
    finally:write(path,original)


@pytest.mark.parametrize('arm',['strict_validation','native_pareto'])
def test_native_local_gate_cannot_be_bypassed_for_validation(tmp_path,config,models,initial,arm):
    fake=Fake('no_local_gain');run=tmp_path/'runtime';run.mkdir()
    rt=Runtime(run,config,models,'fake',fake);rt.bind_arm(arm)
    result=run_repeat(rt,config,initial,rows('optimize',6),rows('validation',4),run/'cell',1)
    assert result['generated']>0 and result['native_accepted']==0
    changed_validation=[r for role,r in fake.calls if role=='solver' and
        'validation' in r['messages'][1]['content'] and 'carefully' in r['messages'][0]['content'].lower()]
    assert changed_validation==[], 'local-failing candidate must never receive native full Validation'


def test_current_best_retains_tie_archive_but_never_switches_parent(tmp_path,config,models,initial):
    fake=Fake('val_tie');run=tmp_path/'runtime';run.mkdir()
    rt=Runtime(run,config,models,'fake',fake);rt.bind_arm('strict_validation')
    result=run_repeat(rt,config,initial,rows('optimize',6),rows('validation',4),run/'cell',1)
    native=read(run/'cell/native_result.json');history=read(run/'cell/iterations.json')
    assert len(native['candidates'])>1, 'locally improving globally tied history must stay in the native archive'
    assert native['val_aggregate_scores']==[0.0]*len(native['candidates'])
    assert all(h['parent_native_index']==0 for h in history)
    assert result['selected']==initial and result['validation_correct']==0


def test_arm_approval_precedes_shared_cache_and_repeat_isolation(tmp_path,config,models,initial):
    fake=Fake();rt=Runtime(tmp_path,config,models,'fixture',fake);p=SystemPrompt.from_dict(initial);row=rows('optimize',1)[0]
    rt.bind_arm('strict_validation');rt.register_prompt(p,1);a=rt.prediction(p,row,1,'optimize')
    rt.bind_arm('native_pareto')
    with pytest.raises(Abort,match='UNREGISTERED'):rt.prediction(p,row,1,'optimize')
    rt.register_prompt(p,1);b=rt.prediction(p,row,1,'optimize');assert a==b and len(fake.calls)==1
    rt.register_prompt(p,2);rt.prediction(p,row,2,'optimize');assert len(fake.calls)==2
    assert all('seed' not in req for role,req in fake.calls), 'do not add a new provider seed parameter'


def test_wrong_valid_output_stops_and_truncation_recovers_capacity(tmp_path,config,models,initial):
    replies=iter([response('Final answer:0'),response('partial','length'),response('Final answer:1')]);calls=[]
    def transport(role,request):calls.append(request);return next(replies)
    rt=Runtime(tmp_path,config,models,'fake',transport);rt.bind_arm('strict_validation');p=SystemPrompt.from_dict(initial);rt.register_prompt(p,1)
    data=rows('optimize',2)
    wrong=rt.prediction(p,data[0],1,'optimize');right=rt.prediction(p,data[1],1,'optimize')
    assert wrong['valid'] and not wrong['correct'] and wrong['prediction']['semantic_attempt_count']==1
    assert right['correct'] and right['prediction']['semantic_attempt_count']==2
    assert [r['max_tokens'] for r in calls]==[3600,3600,6144]


def test_test_barrier_and_per_arm_response_ceiling(tmp_path,config,models,initial):
    cfg=deepcopy(config);cfg['training_successful_semantic_and_inflight_ceiling']=1
    rt=Runtime(tmp_path,cfg,models,'fake',Fake());rt.bind_arm('strict_validation');p=SystemPrompt.from_dict(initial);rt.register_prompt(p,1)
    data=rows('optimize',2);rt.prediction(p,data[0],1,'optimize')
    with pytest.raises(Abort,match='CEILING'):rt.prediction(p,data[1],1,'optimize')
    with pytest.raises(Abort,match='RELEASE'):rt.enter_test()


@pytest.mark.parametrize('role,phase',[('test','search'),('shadow','search'),('validation','test')])
def test_split_access_checked_before_file_read(tmp_path,role,phase):
    with pytest.raises(ProtocolViolation,match='ACCESS'):load_rows(tmp_path,role,phase)


def test_flexible_parser_matches_reference_source_process(frozen_reference):
    source=frozen_reference
    fixtures=[('Reasoning first.\nFinal answer: 3','stop'),(r'\boxed{\frac{1}{2}}','stop'),
        ('Final answer: 1\nAnswer: 2','stop'),('3','stop'),('Final answer: 3','length'),
        ('Therefore, the answer is 3.','stop'),('Answer: 3\nThe answer is 3.','stop')]
    command="import json;from dataclasses import asdict;from multi_dataset_diverse_rl.benchmarks.math_flexible_answer import classify_prediction;print(json.dumps([asdict(classify_prediction(*x)) for x in json.loads(input())],sort_keys=True))"
    import os
    env={**os.environ,'PYTHONPATH':str(source)}
    result=subprocess.run([sys.executable,'-c',command],input=json.dumps(fixtures)+'\n',capture_output=True,text=True,
                          cwd=source,env=env,timeout=40,check=True)
    assert json.loads(result.stdout)==[asdict(classify_prediction(*x)) for x in fixtures]


def test_copied_scoring_and_rendering_algorithms_match_frozen_reference_ast(frozen_reference):
    import ast
    source=frozen_reference
    provenance=read(ROOT/'experiments/protocols/gepa_single_prompt_math_seed42_repeat3_v4/copied_scoring_sources.json')
    class DropAdaptedImports(ast.NodeTransformer):
        def visit_ImportFrom(self,node):return None
    def symbol(tree,name):
        return next(n for n in tree.body if getattr(n,'name',None)==name or isinstance(n,ast.Assign) and
                    any(isinstance(t,ast.Name) and t.id==name for t in n.targets))
    for record in provenance['copied']:
        original_path=source/record['source']
        assert file_hash(original_path)==record['source_file_sha256']
        original=ast.parse(original_path.read_text(encoding='utf-8'))
        name=record['symbol']
        if name=='complete_module_except_exception_import':
            local=ast.parse((ROOT/'src/independent_gepa/single_prompt_math/math_flexible_answer.py').read_text(encoding='utf-8'))
            left,right=original,local
        else:
            filename=('prompt.py' if name in ('require_prompt','solver_messages') else
                'math_prediction_validity.py' if name in ('MATHPrediction','MATHResolvedPrediction','resolve_predictions') else 'guards.py')
            local=ast.parse((ROOT/'src/independent_gepa/single_prompt_math'/filename).read_text(encoding='utf-8'))
            left,right=symbol(original,name),symbol(local,name)
        assert ast.dump(DropAdaptedImports().visit(left),include_attributes=False)==ast.dump(DropAdaptedImports().visit(right),include_attributes=False),name


@pytest.mark.parametrize('mutation,expected',[
    ({},'DIRECT_LEVEL_A'),
    ({'provider_usage_details':{}},'EQUIVALENT_LEVEL_B'),
    ({'provider_usage_details':{},'provider_metadata_loss_audited':False},'UNCONFIRMED'),
    ({'provider_body':{'extra':{'thinking_enabled':True}}},'CONTRADICTORY'),
    ({'provider_usage_details':{'completion_tokens_details':{'reasoning_tokens':2}}},'CONTRADICTORY'),
])
def test_reflection_nonthinking_requires_actual_wire_witness(tmp_path,config,models,mutation,expected):
    from independent_gepa.single_prompt_math.runtime import nonthinking_level
    result={**response('fixture'),**mutation}
    rt=Runtime(tmp_path,config,models,'fake',lambda role,request:result);rt.bind_arm('strict_validation')
    request=rt.request('reflection',[{'role':'user','content':'fixture'}])
    assert nonthinking_level(request,result)==expected
    if expected in ('UNCONFIRMED','CONTRADICTORY'):
        with pytest.raises(Abort,match='NONTHINKING'):rt.reflect('fixture',1)
    else:assert rt.reflect('fixture',1)=='fixture'


def test_native_callbacks_do_not_swallow_persistence_failure(monkeypatch):
    from independent_gepa.single_prompt_math.search import History
    import independent_gepa.single_prompt_math.search as search
    def broken(*args,**kwargs):raise OSError('fixture disk error')
    monkeypatch.setattr(search,'write',broken)
    history=History(SimpleNamespace(decisions={}),Path('fixture'))
    with pytest.raises(Abort,match='save:OSError'):history.save()


def test_mathematical_worker_matches_reference_except_local_imports(frozen_reference):
    source=frozen_reference/'multi_dataset_diverse_rl/benchmarks/math_domain_worker.py'
    local=ROOT/'src/independent_gepa/math_comparison/math_domain_worker.py'
    import ast
    def normalized(path):
        tree=ast.parse(path.read_text(encoding='utf-8'))
        tree.body=[n for n in tree.body if not isinstance(n,ast.ImportFrom)]
        return ast.dump(tree,include_attributes=False)
    assert normalized(source)==normalized(local)


@pytest.mark.parametrize('thinking',[False,True])
def test_discarded_reflection_length_retries_missing_witness_but_not_contradiction(tmp_path,config,models,thinking):
    first=response('unfinished','length');first.update(provider_usage_details={},provider_metadata_loss_audited=False)
    if thinking:first['provider_body']={'extra':{'thinking_enabled':True}}
    answers=iter([first,response('complete')]);calls=[]
    def transport(role,request):calls.append(request);return next(answers)
    rt=Runtime(tmp_path,config,models,'fake',transport);rt.bind_arm('strict_validation')
    if thinking:
        with pytest.raises(Abort,match='NONTHINKING'):rt.reflect('fixture',1)
        assert len(calls)==1
    else:
        assert rt.reflect('fixture',1)=='complete' and len(calls)==2
        assert calls[0]==calls[1]



def test_independent_receipt_replay_recovers_local_timeout_without_model_call(complete_fake,monkeypatch):
    import threading
    import independent_gepa.single_prompt_math.audit as audit
    f=complete_fake;calls_before=len(f.fake.calls);ledger_before=file_hash(f.run/'accounting.jsonl')
    original_score=audit.score;original_retry=audit.retry_local_worker;lock=threading.Lock();failed=[False]
    def flaky_score(*args,**kwargs):
        with lock:
            first=not failed[0];failed[0]=True
        if first:raise ProtocolViolation('MATH_EVALUATOR_TIMEOUT')
        return original_score(*args,**kwargs)
    def fast_retry(*args,**kwargs):return original_retry(*args,wait=lambda _:None,**kwargs)
    monkeypatch.setattr(audit,'score',flaky_score);monkeypatch.setattr(audit,'retry_local_worker',fast_retry)
    assert reconcile(f.run,f.bundle,include_test=True)['status']=='PASS'
    assert len(f.fake.calls)==calls_before and file_hash(f.run/'accounting.jsonl')==ledger_before
    records=[json.loads(line) for line in (f.run/'audit_worker_recovery.jsonl').read_bytes().splitlines()]
    assert any(r['category']=='MATH_EVALUATOR_TIMEOUT' for r in records)



@pytest.mark.parametrize('kind',['geometry','gradient','fixed_answer','long','empty','no_op'])
def test_native_only_candidate_policy_has_no_reference_filter(tmp_path,config,models,initial,kind):
    from independent_gepa.single_prompt_math.prompt import solver_messages
    cfg=deepcopy(config);cfg['max_native_iterations']=1
    text={'geometry':'If the problem is geometric, introduce coordinates.',
          'gradient':'Use the gradient to locate stationary points.',
          'fixed_answer':'Always output 7.','long':'A'*4001,'empty':'','no_op':initial['role']}[kind]
    root_system=SystemPrompt.from_dict(initial).render();requests=[]
    def transport(role,request):
        if role=='reflection':
            assert 'maximum_replacement_characters' not in request['messages'][0]['content']
            assert 'never copy example-specific' not in request['messages'][0]['content']
            return response('```\n'+text+'\n```')
        requests.append(deepcopy(request))
        return response('Final answer:'+('1' if request['messages'][0]['content']!=root_system else '0'))
    rt=Runtime(tmp_path,cfg,models,'fake',transport);rt.bind_arm('strict_validation')
    result=run_repeat(rt,cfg,initial,rows('optimize',3),rows('validation',3),tmp_path/'cell',1)
    proposals=read(tmp_path/'cell/proposals.json')
    assert len(proposals)==1 and proposals[0]['candidate']['role']==text
    assert proposals[0]['native_parseable'] and proposals[0]['semantic_guard_evaluated'] is False
    assert result['native_parseable']==1 and result['guard_zero_metrics']==0
    assert result['native_accepted']==(0 if kind=='no_op' else 1)
    assert 'contract_valid' not in proposals[0]


def test_exhausted_reflection_uses_native_no_proposal_instead_of_empty_child(tmp_path,config,models,initial):
    cfg=deepcopy(config);cfg['max_native_iterations']=2;counts={'reflection':0,'solver':0}
    def transport(role,request):
        counts[role]+=1
        return response('unfinished','length') if role=='reflection' else response('Final answer:0')
    rt=Runtime(tmp_path,cfg,models,'fake',transport);rt.bind_arm('native_pareto')
    result=run_repeat(rt,cfg,initial,rows('optimize',3),rows('validation',3),tmp_path/'cell',1)
    assert result['native_iterations']==2 and result['generated']==0 and result['selected']==initial
    assert counts=={'reflection':8,'solver':6} and not rt.failed.is_set()
    assert read(tmp_path/'cell/proposals.json')==[]


def test_native_pareto_can_choose_complementary_lower_aggregate_parent():
    import random
    from gepa.strategies.candidate_selector import ParetoCandidateSelector,CurrentBestCandidateSelector
    state=SimpleNamespace(program_full_scores_val_set=[0.75,0.5],per_program_tracked_scores=[0.75,0.5],
        program_candidates=[{'role':'a'},{'role':'b'}],
        get_pareto_front_mapping=lambda:{0:{0},1:{0},2:{0,1},3:{1}})
    assert CurrentBestCandidateSelector().select_candidate_idx(state)==0
    selector=ParetoCandidateSelector(random.Random(42))
    assert {selector.select_candidate_idx(state) for _ in range(100)}=={0,1}



def test_content_filtered_reflection_skips_native_opportunity_without_aborting(tmp_path,config,models,initial):
    cfg=deepcopy(config);cfg['max_native_iterations']=2;calls=[]
    def transport(role,request):
        calls.append(role)
        return response('','content_filter') if role=='reflection' else response('Final answer:0')
    rt=Runtime(tmp_path,cfg,models,'fake',transport);rt.bind_arm('strict_validation')
    result=run_repeat(rt,cfg,initial,rows('optimize',3),rows('validation',3),tmp_path/'cell',1)
    assert result['generated']==0 and result['native_iterations']==2 and not rt.failed.is_set()
    assert calls.count('reflection')==2


def test_v5_completed_paid_fixture_continuation_requires_no_new_model_calls(complete_fake,tmp_path):
    import shutil
    from independent_gepa.single_prompt_math import continuation
    f=complete_fake;root=tmp_path/'root';parent=root/'runs/parent';parent.parent.mkdir(parents=True)
    shutil.copytree(f.run,parent)
    (root/'configs').mkdir();shutil.copyfile(ROOT/'configs/gepa_single_prompt_scoring_continuation_v5.yaml',
        root/'configs/gepa_single_prompt_scoring_continuation_v5.yaml')
    directory=root/'runs/continuation';receipt=root/'preparation.json'
    prepared=continuation.prepare(root,f.bundle,parent,directory,receipt,fake_fixture=True)
    assert prepared['existing_scores_changed']==0 and len(prepared['reused_test_profiles'])==6
    assert prepared['remaining_test_profiles']==[] and prepared['preparation_model_calls']==0
    parent_hash=prepared['parent_inventory_sha256']
    frozen={'fake_fixture':True,'preparation_path':'preparation.json','run_root':'runs/continuation',
        'policy':continuation.load_policy(root),'parent_attempt_identity':prepared['parent_attempt_identity'],
        'prepared_last_event_sha256':prepared['prepared_last_event_sha256']}
    frozen['identity']=digest(frozen);freeze=root/'continuation.json';write(freeze,frozen)
    def forbidden(*args):pytest.fail('all paid fixture profiles must be reused')
    result=continuation.execute(root,f.bundle,freeze,transport_override=forbidden)
    assert result['status']=='EXECUTION_COMPLETE' and result['additional_physical_attempts']==0
    assert result['additional_charged_tokens']==0
    assert digest(continuation.inventory(parent))==parent_hash
    assert read(directory/'final_audit.json')['status']=='PASS'
    assert read(directory/'final_audit.json')['incomplete_test_preparation_only'] is False
    with pytest.raises(ProtocolViolation,match='REAL_COMPLETED'):
        continuation.publish(root,directory,root/'public')


def test_v5_runtime_missing_test_observation_uses_repaired_score_and_paired_cache(tmp_path,config,models,initial):
    from independent_gepa.single_prompt_math.continuation import TestContinuationRuntime,load_policy
    calls=[]
    def transport(role,request):
        calls.append(role);return response(r'Final answer:(2+\sqrt{2})^{3^{77}-1}')
    rt=TestContinuationRuntime(tmp_path,config,models,'fixture',transport,policy=load_policy(ROOT))
    rt.phase='test';rt.test_release_check=lambda:None;rt.bind_arm('strict_validation')
    prompt=SystemPrompt.from_dict(initial);rt.register_prompt(prompt,1);row=rows('test',1)[0]
    first=rt.prediction(prompt,row,1,'test','final')
    assert first['valid'] and not first['correct'] and calls==['solver']
    rt.bind_arm('native_pareto');rt.register_prompt(prompt,1)
    assert rt.prediction(prompt,row,1,'test','final')==first and calls==['solver']
    assert rt.snapshot()['cache_hits']==1
    with pytest.raises(Abort,match='CONTINUATION_TEST_SOLVER_ONLY'):
        rt.complete('reflection',[],1,'test')
