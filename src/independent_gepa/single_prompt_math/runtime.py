"""Bounded concurrent Solver, durable physical accounting and isolated caches."""
from __future__ import annotations

from concurrent.futures import Future,ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
import os
from pathlib import Path
import threading
import time
from typing import Callable

from ..protocol import ProtocolViolation
from .common import Abort,canonical,digest,read,write,progress
from .math_flexible_answer import classify_prediction
from .math_prediction_validity import resolve_predictions
from .math_domain_v2 import score,worker_deadline
from .prompt import solver_messages
from .recovery import transport_failure,retry_delay,retry_local_worker,TransientProviderPayload,ReflectionUnavailable


def serialized_request(request):
    body=dict(request);extra=body.pop('extra_body',{})
    if not isinstance(extra,dict) or set(extra)&set(body):raise Abort('EXACT_REQUEST_SERIALIZATION_FAILED')
    return canonical({**body,**extra})


def thinking_indicators(body):
    found=[]
    watched={'enable_thinking','thinking','thinking_enabled','thinking_mode','reasoning',
             'reasoning_content','reasoning_text','reasoning_tokens','reasoning_token_count'}
    def walk(value,path='$'):
        if isinstance(value,dict):
            for key,item in value.items():
                child=path+'.'+str(key);name=str(key).lower()
                inactive=item is None or item is False or item==0 or item=='' or item==[] or item=={}
                if isinstance(item,str) and name in {'enable_thinking','thinking','thinking_enabled','thinking_mode'}:
                    inactive=item.lower() in {'false','off','disabled','none','nonthinking','non-thinking'}
                if name in watched and not inactive:found.append(child)
                walk(item,child)
        elif isinstance(value,list):
            for i,item in enumerate(value):walk(item,path+'['+str(i)+']')
    walk(body);return sorted(set(found))


def nonthinking_level(request,result):
    details=(result.get('provider_usage_details') or {}).get('completion_tokens_details') or {}
    reasoning=details.get('reasoning_tokens');chars=result.get('provider_reasoning_character_count')
    present=result.get('provider_reasoning_content_present')
    indicators=result.get('provider_thinking_indicators') or thinking_indicators(result.get('provider_body') or {})
    contradiction=(type(reasoning) is int and reasoning>0) or (chars or 0)>0 or bool(indicators)
    disabled=request.get('extra_body',{}).get('enable_thinking') is False
    common=disabled and chars in (None,0) and present in (False,True) and not contradiction
    direct=common and type(reasoning) is int and reasoning==0
    equivalent=(common and reasoning is None and result.get('finish_reason')=='stop'
                and result.get('provider_metadata_loss_audited') is True
                and result.get('provider_response_accepted') is True)
    return 'DIRECT_LEVEL_A' if direct else 'EQUIVALENT_LEVEL_B' if equivalent else 'CONTRADICTORY' if contradiction else 'UNCONFIRMED'


def validate_response(role,request,result):
    if not isinstance(result,dict) or not isinstance(result.get('text'),str):raise Abort('PROVIDER_TEXT_SERIALIZATION')
    cap=request.get('max_tokens',request.get('max_completion_tokens'))+(10 if role=='reflection' else 0)
    if type(result.get('output_tokens')) is int and result['output_tokens']>cap:raise Abort('PROVIDER_OUTPUT_BOUND_EXCEEDED')
    if role=='reflection':
        level=nonthinking_level(request,result)
        if result.get('finish_reason') in ('length','max_tokens','max_output_tokens'):
            details=(result.get('provider_usage_details') or {}).get('completion_tokens_details') or {}
            reasoning=details.get('reasoning_tokens');chars=result.get('provider_reasoning_character_count')
            if (request.get('extra_body',{}).get('enable_thinking') is not False or level=='CONTRADICTORY'
                or reasoning is not None and type(reasoning) is not int or reasoning not in (None,0)
                or chars not in (None,0)):
                raise Abort('PROVIDER_NONTHINKING_UNCONFIRMED_OR_CONTRADICTORY')
            # Reference amendment: discarded length may lack a witness; it is never accepted.
        elif level not in ('DIRECT_LEVEL_A','EQUIVALENT_LEVEL_B'):
            raise Abort('PROVIDER_NONTHINKING_UNCONFIRMED_OR_CONTRADICTORY')


class Runtime:
    def __init__(self,directory: Path,config: dict,models: dict,identity: str,transport: Callable,
                 source_check: Callable=lambda:None):
        self.directory=directory;self.config=config;self.models=models;self.identity=identity
        self.transport=transport;self.source_check=source_check
        self.lock=threading.RLock();self.failed=threading.Event();self.phase='search'
        self.last_hash='0'*64;self.physical=0;self.successes=0;self.inflight=0;self.charged=0
        self.arm=None;self.arm_successes={arm:0 for arm in config['arms']}
        self.arm_inflight={arm:0 for arm in config['arms']};self.registered=set()
        self.roles={r:{'physical_attempts':0,'successes':0,'charged_tokens':0,'input_tokens':0,
            'output_tokens':0,'fallback_usage_calls':0,'network_failed_attempts':0} for r in ('solver','reflection')}
        self.logical={};self.cache_hits=0;self.cache={};self.futures={}
        self.test_release_check=None;self.provider_cooldowns={};self.retry_categories={}
        self.event('OPEN',attempt_identity=identity,phase=self.phase)

    def event(self,kind: str,**fields):
        with self.lock:
            row={'kind':kind,**fields,'previous_event_sha256':self.last_hash}
            self.last_hash=digest(row)
            with (self.directory/'accounting.jsonl').open('ab') as stream:
                stream.write(canonical({**row,'event_sha256':self.last_hash})+b'\n');stream.flush();os.fsync(stream.fileno())

    def snapshot(self):
        with self.lock:
            return deepcopy({'charged_tokens':self.charged,'physical_attempts':self.physical,
                'successful_semantic_responses':sum(v['successes'] for v in self.roles.values()),
                'phase_successful_semantic_responses':self.successes,'pending_physical_attempts':self.inflight,
                'phase_successful_responses_by_arm':self.arm_successes,
                'roles':self.roles,'transient_failure_attempts_by_category':self.retry_categories,'logical_evaluations':self.logical,'cache_hits':self.cache_hits,
                'last_event_sha256':self.last_hash})

    def guard(self):
        if self.failed.is_set() or (self.directory/'STOP').exists():raise Abort('EXPERIMENT_STOPPED')
        self.source_check()
        if self.phase=='test':
            if self.test_release_check is None:raise Abort('TEST_SELECTION_AND_AUDIT_RELEASE_REQUIRED')
            self.test_release_check()

    def bind_arm(self,arm):
        if arm not in self.config['arms'] or self.inflight:raise Abort('ARM_BINDING_WITH_INFLIGHT_OR_UNKNOWN_ARM')
        self.arm=arm

    def register_prompt(self,prompt,repeat):
        if self.arm not in self.config['arms']:raise Abort('ARM_BINDING_REQUIRED')
        self.registered.add((self.arm,repeat,prompt.prompt_hash))

    def request(self,role: str,messages: list,capacity: int|None=None):
        if role not in self.models['routes']:raise Abort('UNAUTHORIZED_MODEL_ROLE')
        route=self.models['routes'][role]
        request={'model':route['model'],'messages':messages}
        if role=='solver':
            q=self.models['solver_decoding_policy']
            request.update({k:q[k] for k in ('temperature','top_p','presence_penalty','frequency_penalty')})
            request['max_tokens']=capacity or self.models['first_solver_capacity']
        else:
            q=self.models['optimizer_generation_policy']
            request.update({k:q[k] for k in ('temperature','top_p','presence_penalty','frequency_penalty','max_completion_tokens')})
            request['extra_body']={'enable_thinking':False,'top_k':q['top_k']}
            if len(serialized_request(request))+1024>self.models['optimizer_input_limit']:raise Abort('REFLECTION_CONTEXT_LIMIT')
        return request

    def delay(self,seconds):
        deadline=time.monotonic()+seconds
        heartbeat=time.monotonic()+self.config['recovery_wait_heartbeat_seconds']
        self.guard()
        while time.monotonic()<deadline:
            self.guard();self.failed.wait(min(1,max(0,deadline-time.monotonic())))
            if time.monotonic()>=heartbeat:
                progress(f'RECOVERY_WAIT phase={self.phase} arm={self.arm} remaining_seconds={round(max(0,deadline-time.monotonic()))}')
                heartbeat=time.monotonic()+self.config['recovery_wait_heartbeat_seconds']
        self.guard()

    def wait_provider(self,role):
        profile=self.models['routes'][role]['provider_profile']
        while True:
            self.guard()
            with self.lock:remaining=self.provider_cooldowns.get(profile,0)-time.monotonic()
            if remaining<=0:return
            self.delay(remaining)

    def local_worker(self,operation,*,stage,repeat,split,key):
        def record(**event):
            self.event('LOCAL_WORKER_RETRY',phase=self.phase,arm=self.arm,repeat=repeat,split=split,
                       stage=stage,key=key,**event)
            progress(f'LOCAL_WORKER_RETRY stage={stage} phase={self.phase} category={event["category"]} retry={event["retry_index"]}')
        return retry_local_worker(operation,self.config,self.config['local_worker_initial_deadlines_seconds'][self.phase],
                                  check=self.guard,wait=self.delay,on_retry=record)

    def complete(self,role: str,messages: list,repeat: int,split: str,capacity: int|None=None,logical_key: str|None=None):
        if (self.arm not in self.config['arms'] or repeat not in (1,2,3) or self.phase not in ('search','test')
            or self.phase=='search' and (split not in ('optimize','validation') or role=='reflection' and split!='optimize')
            or self.phase=='test' and (split!='test' or role!='solver')):
            raise Abort('ROLE_PHASE_SPLIT_FORBIDDEN')
        request=self.request(role,messages,capacity);cap=request.get('max_tokens',request.get('max_completion_tokens'))
        hard_cap=cap+(10 if role=='reflection' else 0)
        input_bound=len(serialized_request(request))+4096
        bound=input_bound+hard_cap
        retry=0;call_id=None
        while True:
            self.wait_provider(role)
            self.guard()
            with self.lock:
                # A sibling can start a cooldown while this worker waits for the lock.
                profile=self.models['routes'][role]['provider_profile']
                if self.provider_cooldowns.get(profile,0)>time.monotonic():continue
                ceiling=self.config['training_successful_semantic_and_inflight_ceiling' if self.phase=='search'
                                    else 'test_successful_semantic_and_inflight_ceiling']
                if self.arm_successes[self.arm]+self.arm_inflight[self.arm]>=ceiling:raise Abort('SEMANTIC_RESPONSE_AND_INFLIGHT_CEILING')
                self.physical+=1;number=self.physical;self.inflight+=1;self.arm_inflight[self.arm]+=1
                if call_id is None:call_id=number
                self.roles[role]['physical_attempts']+=1
                reservation={'number':number,'phase':self.phase,'arm':self.arm,'repeat':repeat,'split':split,'role':role,
                             'request_sha256':digest(request),'bound':bound,'logical_key':logical_key,
                             'transport_call_id':call_id,'attempt_index':retry+1}
                write(self.directory/'requests'/f'{number:06d}.json',{'request':request,**reservation})
                self.event('RESERVE',**reservation)
            try:
                result=self.transport(role,request)
            except BaseException as exc:
                decision=transport_failure(exc,self.config)
                delay=retry_delay(self.config,retry,decision) if decision.retryable else None
                evidence=getattr(exc,'provider_evidence',None)
                if evidence is None and getattr(exc,'response',None) is not None:
                    evidence={'http_status':exc.response.status_code,'body':exc.response.text}
                with self.lock:
                    self.inflight-=1;self.arm_inflight[self.arm]-=1
                    self.charged+=bound;self.roles[role]['charged_tokens']+=bound
                    self.roles[role]['network_failed_attempts']+=1
                    if decision.retryable:self.retry_categories[decision.category]=self.retry_categories.get(decision.category,0)+1
                    failure={'category':type(exc).__name__,'recovery_category':decision.category,
                             'retryable':decision.retryable,'http_status':decision.http_status,
                             'retry_after_seconds':decision.retry_after_seconds,'provider_evidence':evidence,
                             'typed_detail':str(exc) if isinstance(exc,(Abort,ProtocolViolation)) else None,**reservation}
                    write(self.directory/'failures'/f'{number:06d}.json',failure)
                    self.event('FAILURE_CHARGE',number=number,role=role,amount=bound,
                               category=decision.category,retryable=decision.retryable,http_status=decision.http_status)
                    if decision.retryable:
                        profile=self.models['routes'][role]['provider_profile']
                        self.provider_cooldowns[profile]=max(self.provider_cooldowns.get(profile,0),time.monotonic()+delay)
                        self.event('PROVIDER_RETRY',number=number,arm=self.arm,repeat=repeat,phase=self.phase,
                            split=split,role=role,category=decision.category,http_status=decision.http_status,
                            retry_index=retry+1,delay_seconds=delay,request_sha256=digest(request))
                    write(self.directory/'accounting_snapshot.json',self.snapshot())
                if not decision.retryable:
                    self.failed.set()
                    if isinstance(exc,Abort):raise
                    raise Abort('PROVIDER_TERMINAL_'+type(exc).__name__) from exc
                progress(f'PROVIDER_RETRY role={role} category={decision.category} retry={retry+1} delay_seconds={delay}')
                retry+=1;continue
            result={**result,'network_retry_attempts':retry}
            with self.lock:
                write(self.directory/'responses'/f'{number:06d}.json',{'response':result,**reservation})
                ip,op=result.get('input_tokens'),result.get('output_tokens')
                reliable=(type(ip) is int and type(op) is int and 0<=ip<=input_bound and 0<=op<=hard_cap)
                amount=ip+op if reliable else bound
                self.charged+=amount;self.inflight-=1;self.arm_inflight[self.arm]-=1
                self.successes+=1;self.arm_successes[self.arm]+=1
                u=self.roles[role];u['successes']+=1;u['charged_tokens']+=amount
                if reliable:u['input_tokens']+=ip;u['output_tokens']+=op
                else:u['fallback_usage_calls']+=1
                self.event('RESPONSE_CHARGE',number=number,role=role,amount=amount,
                           response_sha256=digest(result),usage_reliable=reliable)
                write(self.directory/'accounting_snapshot.json',self.snapshot())
            try:validate_response(role,request,result)
            except Abort:self.failed.set();raise
            return result

    def reflect(self,prompt,repeat):
        messages=[{'role':'user','content':prompt}] if isinstance(prompt,str) else prompt
        for draw in range(self.config['reflection_truncation_draws']):
            result=self.complete('reflection',messages,repeat,'optimize')
            if result.get('finish_reason')=='stop' and isinstance(result.get('text'),str):return result['text']
            if result.get('finish_reason')=='content_filter':
                self.event('REFLECTION_UNAVAILABLE',repeat=repeat,category='content_filter')
                raise ReflectionUnavailable('REFLECTION_CONTENT_FILTERED')
            if result.get('finish_reason') not in ('length','max_tokens','max_output_tokens'):
                raise Abort('REFLECTION_FINISH_REASON_FAILURE')
        self.event('REFLECTION_TRUNCATION_EXHAUSTED',repeat=repeat,draws=draw+1)
        raise ReflectionUnavailable('REFLECTION_TRUNCATION_EXHAUSTED')

    def prediction(self,prompt,row,repeat,split,kind='native'):
        self.guard()
        if (self.arm,repeat,prompt.prompt_hash) not in self.registered:raise Abort('UNREGISTERED_PROMPT_BEFORE_CACHE_OR_SOLVER')
        if (self.phase=='search' and split not in ('optimize','validation')
            or self.phase=='test' and split!='test'):raise Abort('SOLVER_SPLIT_ACCESS_FORBIDDEN')
        request=self.request('solver',solver_messages(prompt,row['content']['problem']))
        key=digest({'attempt':self.identity,'repeat':repeat,'phase':self.phase,'split':split,
                    'prompt_hash':prompt.prompt_hash,'example_id':row['stable_example_id'],
                    'reference_sha256':digest(row['reference_final_answer']),'request':request})
        with self.lock:
            counter=f'{self.arm}:{kind}:{split}';self.logical[counter]=self.logical.get(counter,0)+1
            self.event('LOGICAL_SOLVER',arm=self.arm,repeat=repeat,phase=self.phase,split=split,kind_of_evaluation=kind,
                       key=key,prompt_hash=prompt.prompt_hash,example_id=row['stable_example_id'])
            if key in self.cache:
                self.cache_hits+=1;self.event('CACHE_HIT',key=key,arm=self.arm,repeat=repeat,split=split)
                return deepcopy(self.cache[key])
            owner=key not in self.futures
            if owner:self.futures[key]=Future()
            future=self.futures[key]
        if not owner:
            value=future.result()
            with self.lock:
                self.cache_hits+=1;self.event('CACHE_HIT',key=key,arm=self.arm,repeat=repeat,split=split)
            return deepcopy(value)
        try:
            attempts=[];network_retries=0
            for draw in range(self.config['solver_semantic_draws']):
                capacity=(self.models['length_recovery_capacity'] if attempts and
                          attempts[-1].finish_reason in ('length','max_tokens','max_output_tokens')
                          else self.models['first_solver_capacity'])
                result=self.complete('solver',request['messages'],repeat,split,capacity,logical_key=key)
                network_retries+=result['network_retry_attempts']
                prediction=self.local_worker(lambda:classify_prediction(result['text'],result.get('finish_reason')),
                    stage='extraction',repeat=repeat,split=split,key=key)
                attempts.append(prediction)
                if prediction.prediction_valid:break
            resolved=resolve_predictions(attempts,transport_retry_attempts=network_retries)
            paid={'prediction':asdict(resolved),'repeat':repeat,'split':split,'phase':self.phase,
                  'example_id':row['stable_example_id'],'prompt_hash':prompt.prompt_hash,'key':key}
            write(self.directory/'resolved_answers'/f'{key}.json',paid)
            correctness=self.local_worker(lambda:score(resolved,row['reference_final_answer']),
                stage='scoring',repeat=repeat,split=split,key=key)
            value={**paid,'correct':correctness,'valid':resolved.prediction_valid,'answer':resolved.answer}
            write(self.directory/'cache'/f'{key}.json',value)
            with self.lock:
                self.cache[key]=deepcopy(value);self.event('SOLVER_RESOLVED',key=key,observation_sha256=digest(value))
                future.set_result(deepcopy(value))
            return value
        except BaseException as exc:
            self.failed.set();future.set_exception(exc)
            if isinstance(exc,Abort):raise
            raise Abort('SOLVER_OPERATIONAL_'+type(exc).__name__+':'+str(exc)) from exc
        finally:
            with self.lock:self.futures.pop(key,None)

    def evaluate(self,prompt,rows,repeat,split,kind='native'):
        workers=self.config['test_solver_concurrency' if self.phase=='test' else 'solver_concurrency']
        with ThreadPoolExecutor(max_workers=workers,thread_name_prefix='gepa_math_solver') as pool:
            return list(pool.map(lambda row:self.prediction(prompt,row,repeat,split,kind),rows))

    def enter_test(self):
        if self.inflight:raise Abort('TEST_PHASE_WITH_INFLIGHT_SEARCH')
        if self.test_release_check is None:raise Abort('TEST_SELECTION_AND_AUDIT_RELEASE_REQUIRED')
        self.test_release_check()
        self.event('SEARCH_ACCOUNTING_CLOSED',snapshot=self.snapshot())
        self.phase='test';self.successes=0;self.arm_successes={a:0 for a in self.config['arms']}
        self.cache={};self.futures={}
        self.event('TEST_PHASE_OPEN',test_access=True)


def real_transport(root: Path,models: dict):
    from openai import OpenAI
    private=root/'runs/provider_credentials.local.json'
    deployment=read(private) if private.exists() else {}
    clients={}
    for role,route in models['routes'].items():
        key=os.environ.get(route['api_key_env']) or deployment.get(route['api_key_env'])
        base=os.environ.get(route['base_url_env']) or deployment.get(route['base_url_env'])
        if not key or not base:raise ProtocolViolation('PROVIDER_CREDENTIALS_UNAVAILABLE_'+route['provider_profile'])
        clients[role]=OpenAI(api_key=key,base_url=base,max_retries=0,timeout=models['provider_timeout_seconds'])
    def transport(role,request):
        raw=clients[role].chat.completions.with_raw_response.create(**request)
        try:
            try:body=raw.http_response.json()
            except ValueError as exc:
                raise TransientProviderPayload('INVALID_JSON',{'http_status':raw.http_response.status_code,'body':raw.http_response.text}) from exc
        finally:raw.http_response.close()
        if role=='reflection' and thinking_indicators(body):
            failure=Abort('PROVIDER_THINKING_CONTROL_FAILURE');failure.provider_evidence={'body':body}
            raise failure
        if isinstance(body,dict) and isinstance(body.get('error'),dict):
            error=body['error'];codes={str(error.get('code','')).lower(),str(error.get('type','')).lower()}
            if codes & {'invalid_api_key','authentication_error','permission_error','model_not_found','invalid_request_error'}:
                raise ProtocolViolation('PERMANENT_PROVIDER_ERROR_ENVELOPE')
        try:
            choice=body['choices'][0];message=choice['message']
            if ('content' not in message or not isinstance(message['content'],(str,type(None)))
                or not isinstance(choice.get('finish_reason'),str)):
                raise ValueError('invalid completion envelope')
        except (KeyError,IndexError,TypeError,AttributeError,ValueError) as exc:
            raise TransientProviderPayload('INVALID_ENVELOPE',{'body':body}) from exc
        usage=body.get('usage') or {}
        if not isinstance(usage,dict) or not isinstance(usage.get('completion_tokens_details') or {},dict):
            raise TransientProviderPayload('INVALID_ENVELOPE',{'body':body})
        details=usage.get('completion_tokens_details') or {};reasoning=choice['message'].get('reasoning_content')
        return {'text':message['content'] if message['content'] is not None else '',
                'finish_reason':choice.get('finish_reason'),
                'input_tokens':usage.get('prompt_tokens'),'output_tokens':usage.get('completion_tokens'),
                'reasoning_tokens':details.get('reasoning_tokens'),
                'reasoning_character_count':len(reasoning) if isinstance(reasoning,str) else 0,
                'provider_usage_details':usage,
                'provider_reasoning_character_count':len(reasoning) if isinstance(reasoning,str) else None,
                'provider_reasoning_content_present':'reasoning_content' in choice['message'],
                'provider_response_accepted':True,'provider_metadata_loss_audited':'content' in choice['message'],
                'provider_thinking_indicators':thinking_indicators(body),'provider_body':body}
    return transport,clients
