"""Independent request, cache, native selection and terminal-score reconciliation."""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
import os
import threading
from pathlib import Path

from ..protocol import ProtocolViolation
from .bundle import load_rows,validate_bundle
from .common import Abort,digest,read,canonical
from .math_flexible_answer import classify_prediction
from .math_prediction_validity import resolve_predictions
from .math_domain_v2 import worker_deadline
from .scoring import score
from .prompt import SystemPrompt,solver_messages
from .runtime import Runtime,serialized_request,validate_response
from .recovery import retry_local_worker,retry_delay,RetryDecision


def reconcile(directory: Path,bundle: Path,*,include_test: bool=False,check=None,
              scoring_function=None,recovery_policy_config=None,allow_incomplete_test=False,terminal_repair_policy=None) -> dict:
    validate_bundle(bundle);frozen=read(directory/'frozen.json');identity=frozen['identity'];cfg=frozen['config']
    def audit_guard():
        if (directory/'STOP').exists():raise Abort('EXPERIMENT_STOPPED')
        if check is not None:check()
    audit_guard()
    from ..math_scoring import CONTRACT_ID,contract_sha256,RetiredMathScorerError
    if (scoring_function is not None or recovery_policy_config is not None or terminal_repair_policy is not None
        or cfg.get('scoring_policy')!=CONTRACT_ID or cfg.get('math_scoring_sha256')!=contract_sha256()):
        raise RetiredMathScorerError('CURRENT_AUDIT_REQUIRES_SOLE_HENDRYCKS_SCORER')
    score_function=score
    replay_config=cfg
    initial=SystemPrompt.from_dict(read(bundle/'initial.json'));models=read(bundle/'model_contract.json')
    prototype=Runtime.__new__(Runtime);prototype.models=models
    splits={s:load_rows(bundle,s,'search') for s in ('optimize','validation')}
    if include_test:
        from .heldout import load_test,contract
        splits['test']=load_test(bundle,frozen.get('test_contract') or contract(bundle),directory.parent.parent)
    by_id={s:{r['stable_example_id']:r for r in rows} for s,rows in splits.items()}
    prompts={};proposals={}
    for arm in cfg['arms']:
        for repeat in cfg['repeat_ids']:
            prompts[(arm,repeat,initial.prompt_hash)]=initial
            path=directory/arm/f'repeat_{repeat}/proposals.json'
            for row in read(path) if path.exists() else []:
                proposals[(arm,repeat,row['generation'])]=row
                if row['native_parseable']:
                    prompt=SystemPrompt.from_dict(row['candidate'])
                    if prompt.prompt_hash!=row['candidate_hash']:raise ProtocolViolation('AUDIT_CANDIDATE_HASH')
                    prompts[(arm,repeat,prompt.prompt_hash)]=prompt
    registered={(a,r,initial.prompt_hash) for a in cfg['arms'] for r in cfg['repeat_ids']}
    pending={};seen=set();responses={};failures=Counter();resolved={};logical=Counter();hits=0
    physical=Counter();charged=Counter();previous='0'*64;requests_by_key={};test_open=False
    logical_contexts=set();successes=Counter();logical_by_cell=Counter()
    calls={};awaiting_retry={};ready_retry=set();retry_categories=Counter();role_failures=Counter()
    allowed_kinds={'OPEN','CANDIDATE_REGISTERED','LOGICAL_SOLVER','RESERVE','FAILURE_CHARGE','RESPONSE_CHARGE',
        'CACHE_HIT','SOLVER_RESOLVED','REFLECTION_TRUNCATION_EXHAUSTED','SAME_PAID_ANSWER_LOCAL_SCORE_TIMEOUT',
        'SAME_PAID_ANSWER_EXTRACTION_TIMEOUT','SEARCH_ACCOUNTING_CLOSED','TEST_PHASE_OPEN','PROVIDER_RETRY','LOCAL_WORKER_RETRY','REFLECTION_UNAVAILABLE'}
    for line in (directory/'accounting.jsonl').read_bytes().splitlines():
        event=json.loads(line);value=dict(event);sha=value.pop('event_sha256')
        if digest(value)!=sha or value['previous_event_sha256']!=previous:
            raise ProtocolViolation('AUDIT_ACCOUNTING_HASH_CHAIN')
        previous=sha;kind=event['kind']
        if kind not in allowed_kinds:raise ProtocolViolation('AUDIT_UNKNOWN_EVENT')
        if kind=='OPEN' and event['attempt_identity']!=identity:raise ProtocolViolation('AUDIT_ATTEMPT_IDENTITY')
        if kind=='TEST_PHASE_OPEN':
            if not include_test or not (directory/'SEARCH_COMPLETE.json').exists():raise ProtocolViolation('AUDIT_TEST_ACCESS')
            test_open=True
        if kind=='CANDIDATE_REGISTERED':
            row=dict(proposals[(event['arm'],event['repeat'],event['generation'])])
            row.pop('native_candidate_index',None);row.pop('native_rejection_reason',None)
            row.update(native_accepted=False,local_positive=None)
            if (digest(row)!=event['registration_sha256'] or row.get('semantic_guard_evaluated') is not False
                or row.get('guard_policy')!='native_only'):
                raise ProtocolViolation('AUDIT_CANDIDATE_REGISTERED_EVENT')
            registered.add((event['arm'],event['repeat'],event['candidate_hash']))
        elif kind=='LOGICAL_SOLVER':
            arm=event['arm'];repeat=event['repeat'];split=event['split'];phase=event['phase'];prompt=prompts.get((arm,repeat,event['prompt_hash']))
            if prompt is None or (arm,repeat,prompt.prompt_hash) not in registered:raise ProtocolViolation('AUDIT_UNREGISTERED_LOGICAL_SOLVER')
            if split not in by_id or event['example_id'] not in by_id[split]:raise ProtocolViolation('AUDIT_LOGICAL_MEMBERSHIP')
            if (phase=='test' and (not test_open or split!='test') or phase=='search' and split not in ('optimize','validation')):
                raise ProtocolViolation('AUDIT_LOGICAL_PHASE')
            row=by_id[split][event['example_id']]
            request=prototype.request('solver',solver_messages(prompt,row['content']['problem']))
            from ..math_scoring.prediction import cache_identity
            key=digest({**cache_identity(),'attempt':identity,'repeat':repeat,'phase':phase,'split':split,
                'prompt_hash':prompt.prompt_hash,'example_id':row['stable_example_id'],
                'reference_sha256':digest(row['reference_final_answer']),'request':request})
            if key!=event['key']:raise ProtocolViolation('AUDIT_LOGICAL_CACHE_IDENTITY')
            seen.add(key);logical_contexts.add((arm,key));requests_by_key[key]=(repeat,phase,split,prompt.prompt_hash,row)
            logical[f'{arm}:{event["kind_of_evaluation"]}:{split}']+=1
            logical_by_cell[(arm,repeat,event['kind_of_evaluation'])]+=1
        elif kind=='RESERVE':
            number=event['number'];receipt=read(directory/'requests'/f'{number:06d}.json');request=receipt['request']
            if number in pending or digest(request)!=event['request_sha256'] or any(receipt[k]!=event[k] for k in ('arm','repeat','phase','split','role','bound','logical_key','transport_call_id','attempt_index')):
                raise ProtocolViolation('AUDIT_WIRE_RESERVATION')
            arm=event['arm'];role=event['role'];phase=event['phase'];split=event['split'];repeat=event['repeat'];key=None
            call=event['transport_call_id'];attempt=event['attempt_index']
            signature=tuple(event[k] for k in ('arm','repeat','phase','split','role','logical_key','request_sha256'))
            if attempt==1:
                if call!=number or call in calls:raise ProtocolViolation('AUDIT_TRANSPORT_CALL_IDENTITY')
                calls[call]=(signature,1)
            else:
                if call not in calls or calls[call]!=(signature,attempt-1) or call in awaiting_retry or call not in ready_retry:
                    raise ProtocolViolation('AUDIT_RETRY_REQUEST_CHANGED_OR_UNRECORDED')
                calls[call]=(signature,attempt);ready_retry.remove(call)
            if (phase not in ('search','test') or phase=='test' and (not test_open or role!='solver' or split!='test')
                or phase=='search' and (split not in ('optimize','validation') or role=='reflection' and split!='optimize')):
                raise ProtocolViolation('AUDIT_PHYSICAL_ROLE_PHASE')
            capacity=request.get('max_tokens') if role=='solver' else None
            if request!=prototype.request(role,request['messages'],capacity):raise ProtocolViolation('AUDIT_DECODING_OR_MODEL')
            if role=='solver':
                if capacity not in (3600,6144) or len(request['messages'])!=2:raise ProtocolViolation('AUDIT_SOLVER_INTERFACE')
                key=event.get('logical_key')
                if key not in requests_by_key:raise ProtocolViolation('AUDIT_SOLVER_WITHOUT_LOGICAL_CONTEXT')
                context=requests_by_key[key]
                if context[:3]!=(repeat,phase,split):raise ProtocolViolation('AUDIT_SOLVER_LOGICAL_CONTEXT_MISMATCH')
                row=context[4];prompt=prompts[(arm,repeat,context[3])]
                if request['messages']!=solver_messages(prompt,row['content']['problem']):raise ProtocolViolation('AUDIT_SOLVER_MESSAGE_ROLES')
                base=prototype.request('solver',request['messages'])
                from ..math_scoring.prediction import cache_identity
                expected_key=digest({**cache_identity(),'attempt':identity,'repeat':repeat,'phase':phase,'split':split,
                    'prompt_hash':prompt.prompt_hash,'example_id':row['stable_example_id'],
                    'reference_sha256':digest(row['reference_final_answer']),'request':base})
                if key!=expected_key:raise ProtocolViolation('AUDIT_SOLVER_LOGICAL_REQUEST_MISMATCH')
                if key not in seen or (arm,key) not in logical_contexts or key in resolved:raise ProtocolViolation('AUDIT_UNREQUESTED_OR_REPEATED_PROVIDER_REALIZATION')
                prior=responses.get(key,[])
                expected=6144 if prior and prior[-1]['finish_reason'] in ('length','max_tokens','max_output_tokens') else 3600
                if capacity!=expected:raise ProtocolViolation('AUDIT_RECOVERY_CAPACITY')
            ceiling=cfg['training_successful_semantic_and_inflight_ceiling' if phase=='search' else 'test_successful_semantic_and_inflight_ceiling']
            active=sum(r['phase']==phase and r['arm']==arm for r,k in pending.values())
            if successes[(phase,arm)]+active>=ceiling:raise ProtocolViolation('AUDIT_PER_ARM_RESOURCE_CEILING')
            cap=request.get('max_tokens',request.get('max_completion_tokens'))+(10 if role=='reflection' else 0)
            if event['bound']!=len(serialized_request(request))+4096+cap:raise ProtocolViolation('AUDIT_RESERVATION_BOUND')
            pending[number]=(event,key);physical[(phase,arm,role)]+=1
        elif kind in ('RESPONSE_CHARGE','FAILURE_CHARGE'):
            reservation,key=pending.pop(event['number']);phase=reservation['phase'];role=reservation['role'];arm=reservation['arm']
            if event['role']!=role or not 0<=event['amount']<=reservation['bound']:raise ProtocolViolation('AUDIT_CHARGE_BOUND')
            charged[(phase,arm,role)]+=event['amount']
            if kind=='FAILURE_CHARGE':
                if event['amount']!=reservation['bound']:raise ProtocolViolation('AUDIT_FAILED_ATTEMPT_NOT_CHARGED')
                receipt=read(directory/'failures'/f'{event["number"]:06d}.json')
                if (receipt['recovery_category']!=event['category'] or receipt['http_status']!=event['http_status']
                    or receipt['retryable'] is not True or event['retryable'] is not True):
                    raise ProtocolViolation('AUDIT_FAILURE_RECEIPT')
                category=receipt['recovery_category'];status=receipt['http_status']
                transient=(category in ('REQUEST_TIMEOUT','CONNECTION_FAILURE','PROVIDER_INVALID_JSON','PROVIDER_INVALID_ENVELOPE')
                    and status is None or category=='HTTP_'+str(status) and type(status) is int
                    and (status in cfg['http_retry_status_codes'] or cfg['http_retry_status_range'][0]<=status<=cfg['http_retry_status_range'][1]))
                if not transient:raise ProtocolViolation('AUDIT_NONTRANSIENT_FAILURE_RETRIED')
                awaiting_retry[reservation['transport_call_id']]=(reservation,receipt)
                retry_categories[category]+=1;role_failures[role]+=1
                if key:failures[key]+=1
                continue
            successes[(phase,arm)]+=1
            response=read(directory/'responses'/f'{event["number"]:06d}.json')['response']
            if digest(response)!=event['response_sha256']:raise ProtocolViolation('AUDIT_RAW_RESPONSE_HASH')
            if response['network_retry_attempts']!=reservation['attempt_index']-1:raise ProtocolViolation('AUDIT_TRANSPORT_RETRY_COUNT')
            request=read(directory/'requests'/f'{event["number"]:06d}.json')['request']
            cap=request.get('max_tokens',request.get('max_completion_tokens'))+(10 if role=='reflection' else 0)
            ip,op=response.get('input_tokens'),response.get('output_tokens')
            reliable=type(ip) is int and type(op) is int and 0<=ip<=reservation['bound']-cap and 0<=op<=cap
            expected=ip+op if reliable else reservation['bound']
            if reliable!=event['usage_reliable'] or expected!=event['amount']:raise ProtocolViolation('AUDIT_RESPONSE_USAGE')
            try:validate_response(role,request,response)
            except BaseException as exc:raise ProtocolViolation('AUDIT_RESPONSE_CONTROL') from exc
            if key:responses.setdefault(key,[]).append(response)
        elif kind=='PROVIDER_RETRY':
            request=read(directory/'requests'/f'{event["number"]:06d}.json')
            reservation,receipt=awaiting_retry.pop(request['transport_call_id'])
            ready_retry.add(request['transport_call_id'])
            decision=RetryDecision(True,receipt['recovery_category'],receipt['http_status'],receipt['retry_after_seconds'])
            expected=retry_delay(cfg,reservation['attempt_index']-1,decision)
            if (event['number']!=reservation['number'] or event['retry_index']!=reservation['attempt_index']
                or event['delay_seconds']!=expected or event['request_sha256']!=reservation['request_sha256']):
                raise ProtocolViolation('AUDIT_RETRY_BACKOFF_OR_REQUEST')
        elif kind=='LOCAL_WORKER_RETRY':
            if (event['key'] not in requests_by_key or event['category'] not in cfg['local_worker_retry_categories']
                or event['stage'] not in ('extraction','scoring') or event['delay_seconds']!=retry_delay(cfg,event['retry_index']-1)):
                raise ProtocolViolation('AUDIT_LOCAL_WORKER_RETRY')
        elif kind=='SOLVER_RESOLVED':
            key=event['key'];value=read(directory/'cache'/f'{key}.json')
            if digest(value)!=event['observation_sha256'] or key not in requests_by_key or key in resolved:
                raise ProtocolViolation('AUDIT_RESOLVED_OBSERVATION_HASH')
            resolved[key]=value
        elif kind=='CACHE_HIT':
            if event['key'] not in resolved or (event['arm'],event['key']) not in logical_contexts:raise ProtocolViolation('AUDIT_CACHE_WITHOUT_PAID_REALIZATION')
            hits+=1
    if pending or awaiting_retry or ready_retry:raise ProtocolViolation('AUDIT_INFLIGHT_RESERVATIONS')
    if set(resolved)!=seen:raise ProtocolViolation('AUDIT_UNRESOLVED_LOGICAL_EVALUATIONS')
    recovery_lock=threading.Lock()
    def replay(item):
        key,value=item;repeat,phase,split,ph,row=requests_by_key[key]
        def operation():
            predictions=[classify_prediction(r['text'],r.get('finish_reason')) for r in responses[key]]
            if not 1<=len(predictions)<=4 or any(p.prediction_valid for p in predictions[:-1]):
                raise ProtocolViolation('AUDIT_FIRST_VALID_OR_DRAW_BOUND')
            expected=resolve_predictions(predictions,transport_retry_attempts=failures[key])
            if digest(asdict(expected))!=digest(value['prediction']):raise ProtocolViolation('AUDIT_FLEXIBLE_EXTRACTION_OR_RECOVERY')
            if score_function(expected,row['reference_final_answer'])!=value['correct'] or expected.prediction_valid!=value['valid']:
                raise ProtocolViolation('AUDIT_MATHEMATICAL_SCORE')
            return (repeat,phase,split,ph,row['stable_example_id']),value
        def record(**event):
            with recovery_lock:
                with (directory/'audit_worker_recovery.jsonl').open('ab') as stream:
                    stream.write(canonical({'key':key,'include_test':include_test,**event})+b'\n')
                    stream.flush();os.fsync(stream.fileno())
        return retry_local_worker(operation,replay_config,cfg['local_worker_initial_deadlines_seconds'][phase],
                                  check=audit_guard,on_retry=record)
    with ThreadPoolExecutor(max_workers=16) as pool:observations=dict(pool.map(replay,resolved.items()))
    for arm in cfg['arms']:
      for repeat in cfg['repeat_ids']:
        folder=directory/arm/f'repeat_{repeat}';selection=read(folder/'selection.json');native=read(folder/'native_result.json')
        best=max(range(len(native['val_aggregate_scores'])),key=lambda i:native['val_aggregate_scores'][i])
        if (selection['seed']!=42 or selection['selected']!=native['candidates'][best]
            or selection['native_best_index']!=best or candidate_hash_for(selection['selected'])!=selection['selected_hash']):
            raise ProtocolViolation('AUDIT_NATIVE_FINAL_SELECTION')
        for index,candidate in enumerate(native['candidates']):
            ph=candidate_hash_for(candidate);scores=[]
            for i,row in enumerate(splits['validation']):
                obs=observations[(repeat,'search','validation',ph,row['stable_example_id'])]
                actual=float(obs['correct']);recorded=native['val_subscores'][index].get(str(i),native['val_subscores'][index].get(i))
                if actual!=recorded:raise ProtocolViolation('AUDIT_NATIVE_VALIDATION_SCORE')
                scores.append(actual)
            if abs(sum(scores)/len(scores)-native['val_aggregate_scores'][index])>1e-12:
                raise ProtocolViolation('AUDIT_NATIVE_VALIDATION_AGGREGATE')
        generated=[r for (a,rep,n),r in proposals.items() if a==arm and rep==repeat]
        iterations=read(folder/'iterations.json')
        if (len(iterations)>cfg['max_native_proposals'] or len(generated)>len(iterations)
            or selection['generated']!=len(generated) or selection['native_parseable']!=len(generated) or selection.get('semantic_guard_evaluated') is not False):
            raise ProtocolViolation('AUDIT_FUNNEL_OR_ITERATION_BOUND')
        if (selection['full_validation_evaluated']!=len(native['candidates'])-1
            or selection['native_accepted']!=len(native['candidates'])-1
            or selection['validation_improving_over_parent']!=sum(native['val_aggregate_scores'][i]>native['val_aggregate_scores'][native['parents'][i][0]] for i in range(1,len(native['candidates'])))):
            raise ProtocolViolation('AUDIT_FULL_VALIDATION_FUNNEL')
        for filename,ph in (('initial_optimize.json',initial.prompt_hash),('selected_optimize.json',selection['selected_hash'])):
            profile=read(folder/filename)
            if profile!=[observations[(repeat,'search','optimize',ph,row['stable_example_id'])] for row in splits['optimize']]:
                raise ProtocolViolation('AUDIT_OPTIMIZE_DIAGNOSTIC_PROFILE')
        old=[p['correct'] for p in read(folder/'initial_optimize.json')]
        new=[p['correct'] for p in read(folder/'selected_optimize.json')]
        metrics={'initial_optimize_correct':sum(old),'selected_optimize_correct':sum(new),
            'old_correct_retained':sum(a and b for a,b in zip(old,new,strict=True)),
            'old_correct_lost':sum(a and not b for a,b in zip(old,new,strict=True)),
            'newly_correct':sum(not a and b for a,b in zip(old,new,strict=True)),
            'validation_correct':round(native['val_aggregate_scores'][best]*100),
            'initial_validation_correct':round(native['val_aggregate_scores'][0]*100)}
        if any(selection[k]!=v for k,v in metrics.items()):raise ProtocolViolation('AUDIT_SELECTION_METRIC_ARITHMETIC')
        if selection['guard_zero_metrics']!=0 or selection['native_metric_calls']!=logical_by_cell[(arm,repeat,'native')]:
            raise ProtocolViolation('AUDIT_NATIVE_LOGICAL_METRIC_RECONCILIATION')
        verify_selector_trace(cfg,arm,iterations,native,selection)
        if include_test:
            if allow_incomplete_test and not (folder/'test_result.json').exists():continue
            result=read(folder/'test_result.json');profile=read(folder/'test_predictions.json')
            expected=[observations[(repeat,'test','test',selection['selected_hash'],row['stable_example_id'])] for row in splits['test']]
            if profile!=expected or result['correct']!=sum(p['correct'] for p in expected) or result['count']!=300:
                raise ProtocolViolation('AUDIT_FINAL_TEST_PROFILE')
    snapshot=read(directory/'accounting_snapshot.json')
    if (snapshot['charged_tokens']!=sum(charged.values()) or snapshot['physical_attempts']!=sum(physical.values())
        or snapshot['pending_physical_attempts'] or snapshot['cache_hits']!=hits
        or snapshot['logical_evaluations']!=dict(logical)):
        raise ProtocolViolation('AUDIT_FINAL_ACCOUNTING_SNAPSHOT')
    if (snapshot['transient_failure_attempts_by_category']!=dict(retry_categories)
        or any(snapshot['roles'][r]['network_failed_attempts']!=role_failures[r] for r in ('solver','reflection'))):
        raise ProtocolViolation('AUDIT_TRANSIENT_FAILURE_COUNTERS')
    from .conformance import reconcile_v6
    token_ledger=reconcile_v6(directory,cfg,splits)
    if token_ledger.view()['actual_dispatch']['accounted_tokens']!=snapshot['charged_tokens']:
        raise ProtocolViolation('AUDIT_UNIFIED_TOKEN_ACCOUNTING')
    return {'identity':'NATIVE_GEPA_SINGLE_PROMPT_INTEGRITY_AUDIT_V1','status':'PASS','attempt_identity':identity,
        'include_test':include_test,'incomplete_test_preparation_only':allow_incomplete_test,
        'charged_tokens':sum(charged.values()),'physical_attempts':sum(physical.values()),
        'pending_physical_attempts':0,'cache_hits':hits,'logical_evaluations':dict(logical),'resolved_observations':len(resolved),
        'charged_tokens_by_phase_arm_role':{f'{p}:{a}:{r}':n for (p,a,r),n in charged.items()},
        'physical_attempts_by_phase_arm_role':{f'{p}:{a}:{r}':n for (p,a,r),n in physical.items()},
        'last_event_sha256':previous,'new_model_calls_by_audit':0,'paid_terminal_repairs':0}


def candidate_hash_for(candidate):
    return SystemPrompt.from_dict(candidate).prompt_hash


def verify_selector_trace(config,arm,iterations,native,selection):
    previous_score=-1;previous_parent=None
    for row in iterations:
        scores=row['pool_validation_scores_before'];index=row['parent_native_index']
        if scores!=native['val_aggregate_scores'][:len(scores)] or not 0<=index<len(scores):
            raise ProtocolViolation('AUDIT_PARENT_POOL_TRACE')
        if row['parent_hash']!=candidate_hash_for(native['candidates'][index]) or row['parent_validation_score']!=scores[index]:
            raise ProtocolViolation('AUDIT_PARENT_IDENTITY_OR_VALIDATION_TRACE')
        if config['selectors'][arm]=='current_best':
            best=max(range(len(scores)),key=lambda i:scores[i])
            if index!=best or scores[index]<previous_score:
                raise ProtocolViolation('AUDIT_GREEDY_CURRENT_BEST_PARENT')
            if previous_parent is not None and row['parent_hash']!=previous_parent and scores[index]<=previous_score:
                raise ProtocolViolation('AUDIT_GREEDY_TIE_REPLACED_INCUMBENT')
            previous_score=scores[index];previous_parent=row['parent_hash']
    if selection['selector']!=config['selectors'][arm]:raise ProtocolViolation('AUDIT_SELECTOR_IDENTITY')
