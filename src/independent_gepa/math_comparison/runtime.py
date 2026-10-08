"""Single-owner, journal-first accounting and resolved member/window cache."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

from ..protocol import ProtocolViolation
from .benchmark import classify, correct
from .contract import digest, read, write

class ExecutionAbort(BaseException):
    """Fail closed even inside optimizer exception handlers."""

def append(path: Path, value: Any) -> None:
    with path.open('a',encoding='utf-8',newline='\n') as stream:
        stream.write(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n')
        stream.flush(); os.fsync(stream.fileno())

def wire_bytes(request: dict[str,Any]) -> bytes:
    return json.dumps(request,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')

class Runtime:
    def __init__(self, private: Path, config: dict[str,Any], models: dict[str,Any], shell: dict[str,str],
                 identity: str, transport: Callable[[dict[str,Any]],dict[str,Any]]):
        self.private=private; self.config=config; self.models=models; self.shell=shell
        self.identity=identity; self.transport=transport; self.cache: dict[str,dict[str,Any]]={}
        self.charged=0; self.reserved=0; self.physical=0; self.successes=0; self.cache_hits=0
        self.role_usage={r:{'physical_attempts':0,'successes':0,'input_tokens':0,'output_tokens':0,
                            'charged_tokens':0} for r in ('solver','reflection')}
        self.logical={p:0 for p in ('search','baseline','audit')}; self.last_hash='0'*64
        self.source_check=None; self.active_role=None
        self.candidate_checks: dict[tuple[int,int],Callable[[str],dict[str,Any]]]={}
        self.final_review_check=None
        self.event({'kind':'OPEN','identity':identity,'ceiling':config['token_ceiling']})

    def event(self, value: dict[str,Any]) -> None:
        value={**value,'previous_event_sha256':self.last_hash}
        self.last_hash=digest(value); append(self.private/'accounting.jsonl',{**value,'event_sha256':self.last_hash})

    def snapshot(self) -> dict[str,Any]:
        return {'charged_tokens':self.charged,'reserved_inflight':self.reserved,'physical_attempts':self.physical,
                'provider_successes':self.successes,'cache_hits':self.cache_hits,'logical_evaluations':self.logical,
                'role_usage':self.role_usage,'last_event_sha256':self.last_hash}

    def request(self,role: str,messages: list[dict[str,str]]) -> dict[str,Any]:
        if role=='solver':
            p=self.models['solver_decoding_policy']
            return {'model':self.models['models']['solver'],'messages':messages,
                **{k:p[k] for k in ('temperature','top_p','top_k','min_p','presence_penalty','frequency_penalty','enable_thinking')},
                'max_tokens':p['max_output_tokens']}
        p=self.models['optimizer_generation_policy']
        return {'model':p['model'],'messages':messages,
            **{k:p[k] for k in ('temperature','top_p','top_k','presence_penalty','frequency_penalty','enable_thinking')},
            'max_completion_tokens':p['max_completion_tokens']}

    def complete(self,role: str,request: dict[str,Any],window: int,phase: str) -> dict[str,Any]:
        cap=request.get('max_tokens',request.get('max_completion_tokens'))+(10 if role=='reflection' else 0)
        bound=len(wire_bytes(request))+4096+cap
        for retry in range(self.models['decoding']['transport_retries']+1):
            if self.source_check is not None: self.source_check()
            if self.charged+bound>self.config['token_ceiling'] or self.physical>=self.config['physical_attempt_ceiling']:
                raise ExecutionAbort('RESOURCE_CEILING_BEFORE_TRANSPORT')
            self.physical+=1; self.reserved=bound; self.active_role=role; usage=self.role_usage[role]; usage['physical_attempts']+=1
            reservation={'kind':'RESERVE','physical_attempt':self.physical,'amount':bound,
                         'role':role,'window':window,'phase':phase,'request_sha256':digest(request)}
            self.event(reservation)
            write(self.private/'requests'/f'{self.physical:06d}.json',{'request':request,'reservation':reservation})
            try:
                result=self.transport(request)
            except Exception as exc:
                # Unknown usage is conservatively charged; no zero-cost failed requests.
                self.charged+=bound; self.reserved=0; usage['charged_tokens']+=bound
                self.event({'kind':'FAILURE_CHARGE','physical_attempt':self.physical,'amount':bound,
                            'role':role,'category':type(exc).__name__})
                write(self.private/'failures'/f'{self.physical:06d}.json',{'category':type(exc).__name__,
                    'role':role,'window':window,'phase':phase,'request_sha256':digest(request)})
                write(self.private/'accounting_snapshot.json',self.snapshot())
                from openai import APIConnectionError,APITimeoutError,RateLimitError,InternalServerError
                if not isinstance(exc,(APIConnectionError,APITimeoutError,RateLimitError,InternalServerError)) or retry==self.models['decoding']['transport_retries']:
                    raise ExecutionAbort('PROVIDER_TERMINAL_'+type(exc).__name__) from exc
                time.sleep(min(1.5*2**retry,60)); continue
            # Persist full response before reconciliation. This directory is ignored.
            write(self.private/'responses'/f'{self.physical:06d}.json',{'request':request,'response':result,
                'role':role,'window':window,'phase':phase,'reservation':reservation})
            ip,op=result.get('input_tokens'),result.get('output_tokens')
            reliable=type(ip) is int and type(op) is int and 0<=ip<=bound-cap and 0<=op<=cap
            charge=ip+op if reliable else bound
            self.charged+=charge; self.reserved=0; usage['charged_tokens']+=charge
            self.event({'kind':'RESPONSE_CHARGE','physical_attempt':self.physical,'amount':charge,
                'role':role,'response_sha256':digest(result),'usage_reliable':reliable})
            if not reliable: raise ExecutionAbort('PROVIDER_USAGE_INVALID')
            self.successes+=1; usage['successes']+=1; usage['input_tokens']+=ip; usage['output_tokens']+=op
            write(self.private/'accounting_snapshot.json',self.snapshot())
            if result.get('reasoning_character_count',0) or (result.get('reasoning_tokens') or 0)>0:
                raise ExecutionAbort('PROVIDER_THINKING_CONTROL_FAILURE')
            if role=='reflection' and (result.get('finish_reason')!='stop' or not isinstance(result.get('text'),str)):
                raise ExecutionAbort('REFLECTION_OUTPUT_CONTRACT_FAILURE')
            return result
        raise ExecutionAbort('UNREACHABLE_TRANSPORT_STATE')

    def solve(self,prompt: str,example: dict[str,Any],window: int,member: int,phase: str) -> dict[str,Any]:
        if phase not in self.logical: raise ProtocolViolation('HELDOUT_ACCESS_FORBIDDEN')
        if self.source_check is not None:self.source_check()
        if self.config.get('candidate_review_policy')=='owner_semantic_before_solver_v1' and phase!='search':
            if self.final_review_check is None:raise ExecutionAbort('FINAL_CONFORMANCE_REQUIRED_BEFORE_FULL')
            self.final_review_check()
        if self.config.get('candidate_review_policy')=='owner_semantic_before_solver_v1' and prompt!='Solve the problem.':
            check=self.candidate_checks.get((window,member))
            if check is None or not check(prompt)['contract_valid']:
                raise ExecutionAbort('UNAPPROVED_CHANGED_PROCEDURE_BEFORE_SOLVER')
        self.logical[phase]+=1
        messages=[{'role':'system','content':self.shell['system']},
                  {'role':'user','content':prompt+'\n\n'+example['problem']+self.shell['suffix']}]
        request=self.request('solver',messages)
        key=digest({'attempt':self.identity,'window':window,'member':member,'request':request})
        if key in self.cache:
            self.cache_hits+=1; self.event({'kind':'CACHE_HIT','role':'solver','window':window,'phase':phase,'key':key})
            return self.cache[key]
        attempts=[]
        for _ in range(4):
            result=self.complete('solver',request,window,phase)
            prediction=classify(result.get('text'),result.get('finish_reason')); attempts.append(prediction)
            if prediction['prediction_valid']: break
        prediction={**attempts[-1],'semantic_attempt_count':len(attempts),
            'raw_invalid_count':sum(not p['prediction_valid'] for p in attempts),
            'terminal_invalid':not attempts[-1]['prediction_valid'], 'original_predictions':attempts}
        prediction['correct']=correct(prediction,example['reference'])
        text=prediction.get('text','')
        prediction['immutable_single_line_obeyed']=bool(isinstance(text,str) and re.fullmatch(r'FINAL_ANSWER:[^\r\n]+',text.strip()))
        self.cache[key]=prediction
        write(self.private/'cache'/f'{key}.json',prediction)
        return prediction

    def reflect(self,prompt: str|list[dict[str,str]],window: int) -> str:
        messages=[{'role':'user','content':prompt}] if isinstance(prompt,str) else prompt
        return self.complete('reflection',self.request('reflection',messages),window,'search')['text']

def real_transport(models: dict[str,Any]):
    """Use the A4 provider profile; serialize and transmit the reserved exact bytes."""
    import httpx
    from openai import OpenAI,APIConnectionError,APITimeoutError
    from openai._models import FinalRequestOptions
    api_key=os.environ.get('LWJ_DASHSCOPE_API_KEY'); base_url=os.environ.get('LWJ_DASHSCOPE_BASE_URL')
    if not api_key or not base_url: raise ProtocolViolation('LWJ_PROVIDER_CREDENTIALS_UNAVAILABLE')
    client=OpenAI(api_key=api_key,base_url=base_url,max_retries=0,timeout=models['decoding']['timeout_seconds'])
    def transport(request: dict[str,Any]) -> dict[str,Any]:
        options=FinalRequestOptions.construct(method='post',url='/chat/completions',security={'bearer_auth':True})
        wire=client._client.build_request('POST',client._prepare_url('/chat/completions'),
            headers=client._build_headers(options),content=wire_bytes(request))
        try: response=client._client.send(wire,follow_redirects=False)
        except httpx.TimeoutException as exc: raise APITimeoutError(request=wire) from exc
        except httpx.TransportError as exc: raise APIConnectionError(request=wire) from exc
        try:
            if response.is_error or response.is_redirect: raise client._make_status_error_from_response(response)
            body=response.json(); choice=body['choices'][0]; usage=body.get('usage',{})
            details=usage.get('completion_tokens_details') or {}
            reasoning=choice['message'].get('reasoning_content')
            return {'text':choice['message'].get('content'),'finish_reason':choice.get('finish_reason'),
                'input_tokens':usage.get('prompt_tokens'),'output_tokens':usage.get('completion_tokens'),
                'reasoning_tokens':details.get('reasoning_tokens'),
                'reasoning_character_count':len(reasoning) if isinstance(reasoning,str) else 0,
                'provider_body':body}
        finally: response.close()
    return transport,client

def audit_accounting(private: Path) -> dict[str,Any]:
    previous='0'*64; reserves={}; charged=0; physical=0; usage_by_role={'solver':0,'reflection':0}
    for line in (private/'accounting.jsonl').read_text(encoding='utf-8').splitlines():
        row=json.loads(line); identity=row.pop('event_sha256')
        if row['previous_event_sha256']!=previous or digest(row)!=identity:
            raise ProtocolViolation('ACCOUNTING_HASH_CHAIN_FAILURE')
        previous=identity
        if row['kind']=='RESERVE':
            if row['physical_attempt'] in reserves: raise ProtocolViolation('DUPLICATE_RESERVATION')
            reserves[row['physical_attempt']]=row['amount']; physical+=1
        elif row['kind'] in {'RESPONSE_CHARGE','FAILURE_CHARGE'}:
            if row['physical_attempt'] not in reserves: raise ProtocolViolation('CHARGE_WITHOUT_RESERVATION')
            if row['kind']=='RESPONSE_CHARGE':
                receipt=read(private/'responses'/f'{row["physical_attempt"]:06d}.json')
                if digest(receipt['response'])!=row['response_sha256'] or receipt['role']!=row['role']:
                    raise ProtocolViolation('RESPONSE_RECEIPT_HASH_MISMATCH')
                if row['usage_reliable'] and row['amount']!=receipt['response']['input_tokens']+receipt['response']['output_tokens']:
                    raise ProtocolViolation('REPORTED_USAGE_CHARGE_MISMATCH')
            del reserves[row['physical_attempt']]; charged+=row['amount']; usage_by_role[row['role']]+=row['amount']
    if reserves: raise ProtocolViolation('UNRESOLVED_RESERVATIONS')
    snapshot=read(private/'accounting_snapshot.json')
    if snapshot['charged_tokens']!=charged or snapshot['physical_attempts']!=physical or snapshot['last_event_sha256']!=previous:
        raise ProtocolViolation('ACCOUNTING_SNAPSHOT_MISMATCH')
    return {'integrity':'PASS','charged_tokens':charged,'physical_attempts':physical,
            'reserved_inflight':0,'role_charged_tokens':usage_by_role,'last_event_sha256':previous}
