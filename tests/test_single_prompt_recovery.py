"""Fault injection for infrastructure-only retries; all transports are offline fixtures."""
from copy import deepcopy
import errno
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from openai import APIConnectionError,APIStatusError,APITimeoutError

from tests.test_single_prompt_math import config,models,initial,response,rows
from independent_gepa.protocol import ProtocolViolation
from independent_gepa.single_prompt_math.common import Abort,read
from independent_gepa.single_prompt_math.prompt import SystemPrompt
from independent_gepa.single_prompt_math.runtime import Runtime,real_transport
from independent_gepa.single_prompt_math.recovery import retry_after,retry_local_worker,TransientProviderPayload


def error(kind,headers=None):
    wire=httpx.Request('POST','https://fixture.invalid/v1')
    if kind=='timeout':return APITimeoutError(request=wire)
    if kind=='connection':return APIConnectionError(request=wire)
    if kind=='payload':return TransientProviderPayload('INVALID_JSON',{'body':'fixture incomplete'})
    return APIStatusError('fixture HTTP failure',response=httpx.Response(kind,headers=headers,request=wire),body={})


def fast_clock(monkeypatch,rt):
    import independent_gepa.single_prompt_math.runtime as runtime
    clock=[1000.0];waits=[]
    monkeypatch.setattr(runtime.time,'monotonic',lambda:clock[0])
    def wait(seconds):rt.guard();waits.append(seconds);clock[0]+=seconds;rt.guard()
    monkeypatch.setattr(rt,'delay',wait)
    return waits,clock


@pytest.mark.parametrize('kind',['timeout','connection','payload',408,409,425,429,500,502,503,504,529,599])
@pytest.mark.parametrize('role',['solver','reflection'])
def test_transient_retries_same_request_receipts_and_single_semantic_draw(tmp_path,config,models,initial,monkeypatch,kind,role):
    config=deepcopy(config);config['training_successful_semantic_and_inflight_ceiling']=1
    calls=[];observed_failure=[]
    def transport(which,request):
        calls.append(deepcopy(request))
        if len(calls)==1:raise error(kind)
        observed_failure.append(read(tmp_path/'failures/000001.json'))
        return response(r'\boxed{0}')
    rt=Runtime(tmp_path,config,models,'fake',transport);rt.bind_arm('strict_validation')
    waits,clock=fast_clock(monkeypatch,rt)
    if role=='solver':
        prompt=SystemPrompt.from_dict(initial);rt.register_prompt(prompt,1)
        value=rt.prediction(prompt,rows('optimize',1)[0],1,'optimize')
        assert value['valid'] and not value['correct']
        assert value['prediction']['semantic_attempt_count']==1 and value['prediction']['transport_retry_attempts']==1
        assert sum(rt.logical.values())==1
    else:assert rt.reflect('fixture reflection',1)==r'\boxed{0}'
    assert calls[0]==calls[1] and waits==[2]
    assert observed_failure[0]['retryable'] is True
    snapshot=rt.snapshot();u=snapshot['roles'][role]
    assert snapshot['physical_attempts']==2 and snapshot['successful_semantic_responses']==1
    assert snapshot['pending_physical_attempts']==0 and u['network_failed_attempts']==1
    assert snapshot['charged_tokens']==observed_failure[0]['bound']+14
    first=read(tmp_path/'requests/000001.json');second=read(tmp_path/'requests/000002.json')
    assert first['transport_call_id']==second['transport_call_id']==1
    assert (first['attempt_index'],second['attempt_index'])==(1,2)


@pytest.mark.parametrize('status',[400,401,403,404,405,413,422])
def test_permanent_status_does_not_loop(tmp_path,config,models,monkeypatch,status):
    calls=[]
    def transport(role,request):calls.append(request);raise error(status)
    rt=Runtime(tmp_path,config,models,'fake',transport);rt.bind_arm('strict_validation')
    waits,clock=fast_clock(monkeypatch,rt)
    with pytest.raises(Abort,match='PROVIDER_TERMINAL'):rt.reflect('fixture',1)
    assert len(calls)==1 and waits==[] and rt.inflight==0
    assert read(tmp_path/'failures/000001.json')['retryable'] is False


def test_backoff_continues_after_many_failures_and_honors_retry_after(tmp_path,config,models,monkeypatch):
    calls=[]
    def transport(role,request):
        calls.append(deepcopy(request))
        if len(calls)<=8:raise error(429,{'retry-after':'90'} if len(calls)==1 else {})
        return response('complete')
    rt=Runtime(tmp_path,config,models,'fake',transport);rt.bind_arm('strict_validation');waits,clock=fast_clock(monkeypatch,rt)
    assert rt.reflect('fixture',1)=='complete'
    assert waits==[90,4,8,16,30,60,60,60]
    assert all(c==calls[0] for c in calls) and rt.successes==1
    assert rt.snapshot()['transient_failure_attempts_by_category']=={'HTTP_429':8}


@pytest.mark.parametrize('headers,expected',[
    ({'retry-after-ms':'2500'},2.5),({'retry-after':'12.5'},12.5),
    ({'retry-after':'Thu, 01 Jan 1970 00:20:00 GMT'},200),
    ({'retry-after-ms':'bad','retry-after':'4'},4),
    ({'retry-after':'nan'},None),({'retry-after':'inf'},None),({'retry-after':'-1'},None),
    ({'retry-after':'not-a-date'},None),({},None)])
def test_retry_after_parsing(headers,expected):assert retry_after(headers,now=1000)==expected


def test_shared_provider_cooldown_does_not_block_other_provider(tmp_path,config,models,monkeypatch):
    rt=Runtime(tmp_path,config,models,'fake',lambda *a:response('fixture'));rt.bind_arm('strict_validation')
    waits,clock=fast_clock(monkeypatch,rt);rt.provider_cooldowns['openlux']=1007
    rt.wait_provider('reflection');assert waits==[]
    rt.wait_provider('solver');assert waits==[7]
    rt.wait_provider('solver');assert waits==[7]


def test_stop_marker_interrupts_recovery_before_next_paid_attempt(tmp_path,config,models,monkeypatch):
    calls=[]
    def transport(*args):calls.append(True);raise error(503)
    rt=Runtime(tmp_path,config,models,'fake',transport);rt.bind_arm('strict_validation')
    def wait(seconds):(tmp_path/'STOP').write_text('user stop');Runtime.delay(rt,seconds)
    monkeypatch.setattr(rt,'delay',wait)
    with pytest.raises(Abort,match='EXPERIMENT_STOPPED'):rt.reflect('fixture',1)
    assert len(calls)==1 and rt.inflight==0 and (tmp_path/'failures/000001.json').exists()


@pytest.mark.parametrize('phase,split',[('search','optimize'),('search','validation'),('test','test')])
@pytest.mark.parametrize('stage',['extraction','scoring'])
def test_local_timeouts_reuse_paid_answer_in_every_split(tmp_path,config,models,initial,monkeypatch,phase,split,stage):
    import independent_gepa.single_prompt_math.runtime as runtime
    from independent_gepa.single_prompt_math.math_domain_v2 import current_worker_deadline
    calls=[];deadlines=[]
    def transport(role,request):calls.append(request);return response(r'\boxed{1}')
    rt=Runtime(tmp_path,config,models,'fake',transport);rt.bind_arm('strict_validation')
    if phase=='test':rt.test_release_check=lambda:None;rt.enter_test()
    rt.phase=phase;waits,clock=fast_clock(monkeypatch,rt)
    name='classify_prediction' if stage=='extraction' else 'score';original=getattr(runtime,name)
    def flaky(*args,**kwargs):
        deadlines.append(current_worker_deadline())
        if len(deadlines)<=2:raise ProtocolViolation('MATH_EVALUATOR_TIMEOUT')
        return original(*args,**kwargs)
    monkeypatch.setattr(runtime,name,flaky)
    prompt=SystemPrompt.from_dict(initial);rt.register_prompt(prompt,1)
    value=rt.prediction(prompt,rows(split,1)[0],1,split)
    assert value['correct'] and len(calls)==1 and value['prediction']['semantic_attempt_count']==1
    assert value['prediction']['transport_retry_attempts']==0 and waits==[2,4]
    assert deadlines==([8,16,32] if phase=='search' else [30,60,120])
    assert rt.charged==14 and rt.successes==1


def test_local_retry_caps_deadline_but_keeps_retrying_and_code_errors_escape(config):
    from independent_gepa.single_prompt_math.math_domain_v2 import current_worker_deadline
    deadlines=[];waits=[]
    def flaky():
        deadlines.append(current_worker_deadline())
        if len(deadlines)<8:raise ProtocolViolation('MATH_EVALUATOR_RESOURCE_TEMPORARY')
        return 42
    assert retry_local_worker(flaky,config,8,wait=waits.append)==42
    assert deadlines==[8,16,32,64,120,120,120,120]
    assert waits==[2,4,8,16,30,60,60]
    def bug():raise ValueError('fixture code defect')
    with pytest.raises(ValueError):retry_local_worker(bug,config,8,wait=lambda _:pytest.fail('code must not retry'))


def test_payload_timeout_not_cached_as_invalid_and_completed_invalid_is_cached(monkeypatch):
    import subprocess
    import independent_gepa.single_prompt_math.payload as payload
    from independent_gepa.single_prompt_math.math_domain_v2 import worker_deadline
    payload.classify_payload.cache_clear();calls=[]
    def run(*args,**kwargs):
        calls.append(kwargs['timeout'])
        if len(calls)==1:raise subprocess.TimeoutExpired('fixture worker',kwargs['timeout'])
        return SimpleNamespace(returncode=0,stdout='{"invalid_reason":"PAYLOAD_PARSE_FAILURE"}')
    monkeypatch.setattr(payload.subprocess,'run',run)
    try:
        with pytest.raises(ProtocolViolation,match='MATH_EVALUATOR_TIMEOUT'):payload.classify_payload('fixture_expression')
        with worker_deadline(16):assert payload.classify_payload('fixture_expression')=='PAYLOAD_PARSE_FAILURE'
        assert payload.classify_payload('fixture_expression')=='PAYLOAD_PARSE_FAILURE' and calls==[8,16]
    finally:payload.classify_payload.cache_clear()


@pytest.mark.parametrize('module_name',['payload','math_domain_v2'])
@pytest.mark.parametrize('error_number',[errno.EAGAIN,errno.ENOMEM,errno.EINTR])
def test_worker_launch_resource_failure_is_typed(monkeypatch,module_name,error_number):
    import importlib
    module=importlib.import_module('independent_gepa.single_prompt_math.'+module_name)
    function=module.classify_payload if module_name=='payload' else module.domain_matrix
    function.cache_clear()
    def failure(*args,**kwargs):raise OSError(error_number,'fixture temporary resource pressure')
    monkeypatch.setattr(module.subprocess,'run',failure)
    with pytest.raises(ProtocolViolation,match='MATH_EVALUATOR_RESOURCE_TEMPORARY'):
        function('fixture' if module_name=='payload' else ('1',))
    function.cache_clear()


@pytest.mark.parametrize('payload_kind',['bad_json','incomplete_envelope'])
def test_actual_sdk_transport_retries_malformed_200_with_raw_receipt(tmp_path,config,models,monkeypatch,payload_kind):
    import openai
    original_client=openai.OpenAI;sent=[]
    def handler(request):
        sent.append(json.loads(request.content))
        if len(sent)==1:
            return httpx.Response(200,text='{"choices":' if payload_kind=='bad_json' else '{}')
        return httpx.Response(200,json={'id':'fixture','choices':[{'message':{'content':r'\boxed{1}'},'finish_reason':'stop'}],
            'usage':{'prompt_tokens':10,'completion_tokens':4,'completion_tokens_details':{'reasoning_tokens':0}}})
    def client(**kwargs):return original_client(http_client=httpx.Client(transport=httpx.MockTransport(handler)),**kwargs)
    monkeypatch.setattr(openai,'OpenAI',client)
    for route in models['routes'].values():
        monkeypatch.setenv(route['api_key_env'],'fixture-key');monkeypatch.setenv(route['base_url_env'],'https://fixture.invalid/v1')
    transport,clients=real_transport(tmp_path,models)
    try:
        rt=Runtime(tmp_path,config,models,'fake',transport);rt.bind_arm('strict_validation');waits,clock=fast_clock(monkeypatch,rt)
        assert rt.reflect('fixture',1)==r'\boxed{1}' and waits==[2]
        assert sent[0]==sent[1] and read(tmp_path/'failures/000001.json')['provider_evidence']
    finally:
        for c in clients.values():c.close()


@pytest.mark.parametrize('exception',[ValueError('fixture code error'),ProtocolViolation('fixture contract error'),Abort('fixture integrity error')])
def test_code_or_integrity_failure_is_not_hidden_by_infinite_retry(tmp_path,config,models,exception):
    calls=[]
    def transport(*args):calls.append(True);raise exception
    rt=Runtime(tmp_path,config,models,'fake',transport);rt.bind_arm('strict_validation')
    with pytest.raises(Abort):rt.reflect('fixture',1)
    assert calls==[True] and rt.failed.is_set() and rt.inflight==0
    assert read(tmp_path/'failures/000001.json')['retryable'] is False



def test_cooldown_started_after_wait_is_rechecked_before_reserving(tmp_path,config,models,monkeypatch):
    observed=[]
    rt=Runtime(tmp_path,config,models,'fake',lambda *args:(observed.append(clock[0]) or response('complete')))
    rt.bind_arm('strict_validation');waits,clock=fast_clock(monkeypatch,rt);original=rt.wait_provider;passed=[False]
    def competing_wait(role):
        original(role)
        if not passed[0]:
            passed[0]=True;rt.provider_cooldowns['lwj']=clock[0]+7
    monkeypatch.setattr(rt,'wait_provider',competing_wait)
    assert rt.reflect('fixture',1)=='complete'
    assert waits==[7] and observed==[1007] and rt.physical==1



@pytest.fixture
def frozen_source_guard(tmp_path,monkeypatch):
    from independent_gepa.single_prompt_math import runner
    from independent_gepa.single_prompt_math.common import file_hash
    gitdir=tmp_path/'.git';gitdir.mkdir();(gitdir/'refs/heads').mkdir(parents=True)
    sha='a'*40;(gitdir/'HEAD').write_text('ref: refs/heads/main\n')
    (gitdir/'refs/heads/main').write_text(sha+'\n')
    source=tmp_path/'source.py';source.write_text('value=1\n')
    inventory={'source.py':file_hash(source)}
    def git(root,*args):
        return str(gitdir) if args[-1] in ('--absolute-git-dir','--git-common-dir') else sha
    monkeypatch.setattr(runner,'git',git);monkeypatch.setattr(runner,'source_inventory',lambda root:inventory)
    return runner.SourceGuard(tmp_path,{'source_sha':sha,'source_inventory':inventory}),source,gitdir


def test_unchanged_source_timestamp_does_not_abort(frozen_source_guard):
    import os
    guard,source,gitdir=frozen_source_guard;stamp=source.stat()
    os.utime(source,ns=(stamp.st_atime_ns,stamp.st_mtime_ns+1000000000));guard();guard()


def test_source_change_still_aborts(frozen_source_guard):
    guard,source,gitdir=frozen_source_guard;source.write_text('value=2\n')
    with pytest.raises(Abort,match='FROZEN_SOURCE_CHANGED'):guard()


def test_git_ref_packing_does_not_abort_but_commit_change_does(frozen_source_guard):
    guard,source,gitdir=frozen_source_guard
    (gitdir/'packed-refs').write_text('# pack-refs with: peeled fully-peeled sorted\n'+'a'*40+' refs/heads/main\n')
    (gitdir/'refs/heads/main').unlink();guard()
    (gitdir/'packed-refs').write_text('b'*40+' refs/heads/main\n')
    with pytest.raises(Abort,match='FROZEN_SOURCE_HEAD_CHANGED'):guard()



def test_broken_progress_output_does_not_abort_network_recovery(tmp_path,config,models,monkeypatch):
    import independent_gepa.single_prompt_math.common as common
    calls=[]
    def transport(*args):
        calls.append(True)
        if len(calls)==1:raise error(503)
        return response('complete')
    def disconnected(*args,**kwargs):raise BrokenPipeError('fixture closed progress pipe')
    monkeypatch.setattr(common,'print',disconnected,raising=False)
    rt=Runtime(tmp_path,config,models,'fake',transport);rt.bind_arm('strict_validation')
    waits,clock=fast_clock(monkeypatch,rt)
    assert rt.reflect('fixture',1)=='complete'
    assert calls==[True,True] and waits==[2] and rt.inflight==0 and not rt.failed.is_set()
    assert read(tmp_path/'responses/000002.json')['response']['network_retry_attempts']==1



@pytest.mark.parametrize('role,finish',[('solver','stop'),('reflection','stop'),('reflection','length')])
def test_native_null_content_is_completed_empty_response_not_infinite_transport_retry(tmp_path,config,models,initial,monkeypatch,role,finish):
    import openai
    original_client=openai.OpenAI;sent=[]
    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200,json={'id':'fixture','choices':[{'message':{'content':None},'finish_reason':finish}],
            'usage':{'prompt_tokens':10,'completion_tokens':4,'completion_tokens_details':{'reasoning_tokens':0}}})
    def client(**kwargs):return original_client(http_client=httpx.Client(transport=httpx.MockTransport(handler)),**kwargs)
    monkeypatch.setattr(openai,'OpenAI',client)
    for route in models['routes'].values():
        monkeypatch.setenv(route['api_key_env'],'fixture-key');monkeypatch.setenv(route['base_url_env'],'https://fixture.invalid/v1')
    transport,clients=real_transport(tmp_path,models)
    try:
        rt=Runtime(tmp_path,config,models,'fake',transport);rt.bind_arm('strict_validation')
        waits,clock=fast_clock(monkeypatch,rt)
        if role=='solver':
            prompt=SystemPrompt.from_dict(initial);rt.register_prompt(prompt,1)
            result=rt.prediction(prompt,rows('optimize',1)[0],1,'optimize')
            assert not result['valid'] and result['prediction']['semantic_attempt_count']==4
            assert result['prediction']['transport_retry_attempts']==0
            expected=4
        else:
            result=rt.complete(role,[{'role':'user','content':'fixture'}],1,'optimize')
            assert result['text']=='' and result['network_retry_attempts']==0
            expected=1
        assert len(sent)==expected and waits==[] and rt.successes==expected
        assert rt.snapshot()['transient_failure_attempts_by_category']=={}
    finally:
        for c in clients.values():c.close()
