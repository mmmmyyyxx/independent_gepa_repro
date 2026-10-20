"""Explicitly authorized continuation of a sealed Test phase, never search resume."""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from functools import partial
from pathlib import Path
import os
import shutil
import threading
import time

from ..protocol import ProtocolViolation
from .common import Abort,canonical,digest,file_hash,git,read,write,source_inventory,require_private,progress
from .bundle import load_rows,validate_bundle
from .prompt import SystemPrompt,solver_messages
from .runtime import Runtime,real_transport
from .runner import SourceGuard,preflight,build_summary
from .audit import reconcile
from .math_flexible_answer import classify_prediction
from .math_prediction_validity import resolve_predictions
from . import scoring_v5,scoring_v7
from .recovery import retry_local_worker


def scoring_module(version):
    if version=='v5':return scoring_v5
    if version=='v7':return scoring_v7
    raise ProtocolViolation('UNKNOWN_CONTINUATION_SCORING_VERSION')


def policy_version(policy):
    identities={'GEPA_SCORING_CONTINUATION_V5':'v5','GEPA_SCORING_CONTINUATION_V7':'v7'}
    try:return identities[policy['identity']]
    except (KeyError,TypeError) as exc:raise ProtocolViolation('UNKNOWN_CONTINUATION_POLICY') from exc


def load_policy(root,version='v5'):
    return scoring_module(version).load_policy(root)


def recovery_config(config,policy):
    return scoring_module(policy_version(policy)).recovery_config(config,policy)


def score(prediction,reference,*,policy):
    return scoring_module(policy_version(policy)).score(prediction,reference,policy=policy)


def inventory(directory):
    return {p.relative_to(directory).as_posix():file_hash(p) for p in sorted(directory.rglob('*')) if p.is_file()}


def append_event(directory,kind,**fields):
    snapshot=read(directory/'accounting_snapshot.json')
    row={'kind':kind,**fields,'previous_event_sha256':snapshot['last_event_sha256']}
    sha=digest(row)
    with (directory/'accounting.jsonl').open('ab') as stream:
        stream.write(canonical({**row,'event_sha256':sha})+b'\n');stream.flush();os.fsync(stream.fileno())
    snapshot['last_event_sha256']=sha;write(directory/'accounting_snapshot.json',snapshot)


def request_key(identity,repeat,prompt,row,models):
    prototype=Runtime.__new__(Runtime);prototype.models=models
    request=prototype.request('solver',solver_messages(prompt,row['content']['problem']))
    return digest({'attempt':identity,'repeat':repeat,'phase':'test','split':'test',
        'prompt_hash':prompt.prompt_hash,'example_id':row['stable_example_id'],
        'reference_sha256':digest(row['reference_final_answer']),'request':request})


def test_record(selection,profile):
    return {'arm':selection['arm'],'repeat_id':selection['repeat_id'],'seed':42,
        'selected_hash':selection['selected_hash'],'correct':sum(v['correct'] for v in profile),
        'count':len(profile),'invalid':sum(not v['valid'] for v in profile)}


def prepare(root,bundle,parent,output,receipt,*,fake_fixture=False,scoring_version='v5',hardlink_immutable=False):
    """Offline copy, same-paid-answer completion and pointwise old-score parity."""
    parent=require_private(root,parent);output=require_private(root,output)
    if output.exists() or receipt.exists():raise ProtocolViolation('FRESH_CONTINUATION_PREPARATION_REQUIRED')
    original=read(parent/'frozen.json');check=dict(original);identity=check.pop('identity')
    if digest(check)!=identity:raise ProtocolViolation('PARENT_FROZEN_IDENTITY')
    if bool(original.get('fake_only_fixture'))!=fake_fixture:raise ProtocolViolation('PARENT_PROVIDER_CLASSIFICATION')
    if not fake_fixture and read(parent/'completion.json').get('status')!='EXECUTION_ABORTED':
        raise ProtocolViolation('STOPPED_PARENT_REQUIRED')
    if read(parent/'accounting_snapshot.json')['pending_physical_attempts']:
        raise ProtocolViolation('PARENT_HAS_INFLIGHT_REQUESTS')
    manifest=validate_bundle(bundle)
    if manifest['bundle_hash']!=original['bundle_hash']:raise ProtocolViolation('PARENT_BUNDLE_CHANGED')
    seal=read(parent/'SEARCH_COMPLETE.json');search=read(parent/'search_audit.json')
    if (seal.get('identity')!=identity or not seal.get('all_searches_closed')
        or len(seal['selections'])!=6 or search.get('status')!='PASS'
        or seal['search_audit_sha256']!=file_hash(parent/'search_audit.json')):
        raise ProtocolViolation('SEALED_COMPLETE_SEARCH_REQUIRED')
    before=inventory(parent)
    def ignored(directory,names):
        return [n for n in names if Path(directory)==parent and n in ('STOP','completion.json','lifecycle.json')]
    def copy_file(source,destination):
        # Append-only journals need private inodes. Other files are immutable
        # or replaced atomically, so writing a new version breaks the link.
        if hardlink_immutable and Path(source).suffix!='.jsonl':return os.link(source,destination)
        return shutil.copy2(source,destination)
    shutil.copytree(parent,output,ignore=ignored,copy_function=copy_file)
    policy=load_policy(root,scoring_version);cfg=recovery_config(original['config'],policy)
    scoring=partial(score,policy=policy)
    contexts={};responses={};failures=Counter();logical_contexts=set();terminals={}
    for line in (output/'accounting.jsonl').read_bytes().splitlines():
        event=__import__('json').loads(line)
        if event['kind']=='LOCAL_WORKER_TERMINAL':
            if event['key'] in terminals:raise ProtocolViolation('DUPLICATE_PARENT_TERMINAL')
            terminals[event['key']]=event
        if event['kind']=='LOGICAL_SOLVER':
            contexts[event['key']]=event;logical_contexts.add((event['arm'],event['key']))
        if event['kind']=='RESERVE' and event['role']=='solver':
            path=output/'responses'/f'{event["number"]:06d}.json';key=event['logical_key']
            if path.exists():responses.setdefault(key,[]).append(read(path)['response'])
            elif (output/'failures'/f'{event["number"]:06d}.json').exists():failures[key]+=1
            else:raise ProtocolViolation('PARENT_RECEIPT_MISSING')
    rows=load_rows(bundle,'test','test');by_id={r['stable_example_id']:r for r in rows};repaired=[]
    for key,context in contexts.items():
        if (output/'cache'/f'{key}.json').exists():continue
        if context['phase']!='test' or context['split']!='test':raise ProtocolViolation('UNRESOLVED_SEARCH_CANNOT_RESUME')
        paid=read(output/'resolved_answers'/f'{key}.json');row=by_id[context['example_id']]
        def operation():
            draws=[classify_prediction(r['text'],r['finish_reason']) for r in responses[key]]
            if not 1<=len(draws)<=4 or any(p.prediction_valid for p in draws[:-1]):raise ProtocolViolation('PAID_DRAW_SEQUENCE')
            resolved=resolve_predictions(draws,transport_retry_attempts=failures[key])
            if digest(asdict(resolved))!=digest(paid['prediction']):raise ProtocolViolation('PAID_RESOLVER_MISMATCH')
            return resolved,scoring(resolved,row['reference_final_answer'])
        resolved,correct=retry_local_worker(operation,cfg,cfg['local_worker_initial_deadlines_seconds']['test'])
        value={**paid,'correct':correct,'valid':resolved.prediction_valid,'answer':resolved.answer}
        write(output/'cache'/f'{key}.json',value)
        append_event(output,'SOLVER_RESOLVED',key=key,observation_sha256=digest(value));repaired.append(key)
        if key in terminals and scoring_version=='v7':
            append_event(output,'PAID_TERMINAL_REPAIRED',key=key,terminal_event_sha256=terminals[key]['event_sha256'],
                policy_sha256=digest(policy),observation_sha256=digest(value),new_model_calls=0)
    from .tokens import TokenLedger
    imported_tokens=TokenLedger.replay(output)
    models=read(bundle/'model_contract.json');reused=[];remaining=[]
    for selection in seal['selections']:
        arm=selection['arm'];repeat=selection['repeat_id'];prompt=SystemPrompt.from_dict(selection['selected'])
        keys=[request_key(identity,repeat,prompt,row,models) for row in rows]
        if all((arm,key) in logical_contexts and (output/'cache'/f'{key}.json').exists() for key in keys):
            profile=[read(output/'cache'/f'{key}.json') for key in keys]
            folder=output/arm/f'repeat_{repeat}';record=test_record(selection,profile)
            for name,value in (('test_predictions.json',profile),('test_result.json',record)):
                path=folder/name
                if path.exists():
                    if read(path)!=value:raise ProtocolViolation('COMPLETED_TEST_PROFILE_CHANGED')
                else:write(path,value)
            if not (folder/'test_accounting.json').exists():
                write(folder/'test_accounting.json',{'arm':arm,'repeat_id':repeat,'wall_seconds':0,
                    'wall_scope':'paid-profile reconstruction only; original partial time unavailable',
                    'tokens':imported_tokens.view('test',arm,repeat)})
            reused.append({'arm':arm,'repeat_id':repeat})
        else:remaining.append({'arm':arm,'repeat_id':repeat})
    audit=reconcile(output,bundle,include_test=True,scoring_function=scoring,
                    recovery_policy_config=cfg,allow_incomplete_test=True,terminal_repair_policy=policy if scoring_version=='v7' else None)
    write(output/'import_audit.json',audit)
    write(output/'lifecycle.json',{'status':'PREPARED','phase':'test','fake_provider':fake_fixture,'attempt_identity':identity})
    if inventory(parent)!=before:raise ProtocolViolation('PARENT_EVIDENCE_CHANGED_DURING_PREPARATION')
    prepared=inventory(output)
    value={'identity':'GEPA_TEST_CONTINUATION_PREPARATION_'+scoring_version.upper(),'status':'PASS','READY_TO_RUN':False,
        'scoring_version':scoring_version,
        'materialization':'hardlink_immutable_private_journals' if hardlink_immutable else 'copy2',
        'parent':parent.relative_to(root).as_posix(),'output':output.relative_to(root).as_posix(),
        'parent_attempt_identity':identity,'bundle_hash':manifest['bundle_hash'],'policy_sha256':digest(policy),
        'parent_inventory':before,'parent_inventory_sha256':digest(before),
        'prepared_inventory':prepared,'prepared_inventory_sha256':digest(prepared),
        'prepared_last_event_sha256':read(output/'accounting_snapshot.json')['last_event_sha256'],
        'import_audit_sha256':file_hash(output/'import_audit.json'),'existing_scores_changed':0,
        'paid_observations_finished':len(repaired),'repaired_keys':repaired,
        'reused_test_profiles':reused,'remaining_test_profiles':remaining,'preparation_model_calls':0,
        'original_accounting':read(parent/'accounting_snapshot.json'),'fake_fixture':fake_fixture}
    write(receipt,value);return value


def freeze(root,bundle,preparation,authorization,gates,output):
    preflight(root,bundle);prep=read(preparation);auth=read(authorization);gate=read(gates)
    version=prep.get('scoring_version','v5')
    policy=load_policy(root,version);current=digest(source_inventory(root));sha=git(root,'rev-parse','HEAD')
    if (gate.get('status')!='PASS' or gate.get('source_inventory_sha256')!=current
        or gate.get('complete_two_arm_three_repeat_fake_e2e')!='PASS'):
        raise ProtocolViolation('CURRENT_COMPLETE_OFFLINE_GATES_REQUIRED')
    if git(root,'diff','--name-only') or git(root,'diff','--cached','--name-only'):
        raise ProtocolViolation('COMMITTED_CONTINUATION_SOURCE_REQUIRED')
    if set(source_inventory(root))-set(git(root,'ls-files').splitlines()):raise ProtocolViolation('UNTRACKED_CONTINUATION_SOURCE')
    if (prep['status']!='PASS' or prep['fake_fixture'] or prep['existing_scores_changed']!=0
        or prep['policy_sha256']!=digest(policy) or prep['bundle_hash']!=validate_bundle(bundle)['bundle_hash']):
        raise ProtocolViolation('CURRENT_CONTINUATION_IMPORT_REQUIRED')
    if inventory(root/prep['parent'])!=prep['parent_inventory'] or inventory(root/prep['output'])!=prep['prepared_inventory']:
        raise ProtocolViolation('SEALED_IMPORT_CHANGED')
    if (auth.get('identity')!='USER_AUTHORIZED_GEPA_SCORING_REPAIR_CONTINUE_'+version.upper() or auth.get('execute') is not True
        or not auth.get('user_request') or auth.get('source_sha')!=sha
        or auth.get('source_inventory_sha256')!=current or auth.get('policy_sha256')!=digest(policy)
        or auth.get('preparation_sha256')!=file_hash(preparation) or auth.get('offline_gate_sha256')!=file_hash(gates)
        or auth.get('run_root')!=prep['output'] or auth.get('roles_by_phase')!={'test':['solver']}
        or auth.get('new_search_calls')!=0 or auth.get('reuse_all_paid_responses') is not True):
        raise ProtocolViolation('EXACT_FRESH_CONTINUATION_AUTHORIZATION_REQUIRED')
    if output.exists():raise ProtocolViolation('FRESH_CONTINUATION_FREEZE_REQUIRED')
    if version=='v7' and (gate.get('v7_engineering_tests_passed',0)<10
        or auth.get('parent_attempt_identity')!=prep['parent_attempt_identity']
        or auth.get('test_contract')!=read(root/prep['parent']/'frozen.json')['test_contract']):
        raise ProtocolViolation('V7_EXACT_POLICY_PARENT_AND_TEST_SCOPE_REQUIRED')
    value={'schema_version':'GEPA_SEALED_TEST_CONTINUATION_'+version.upper(),'source_sha':sha,'source_inventory':source_inventory(root),
        'scoring_version':version,
        'policy':policy,'bundle_hash':prep['bundle_hash'],'parent_attempt_identity':prep['parent_attempt_identity'],
        'config':read(root/prep['parent']/'frozen.json')['config'],
        'preparation_path':preparation.relative_to(root).as_posix(),'preparation_sha256':file_hash(preparation),
        'prepared_last_event_sha256':prep['prepared_last_event_sha256'],'run_root':prep['output'],
        'authorization_path':authorization.relative_to(root).as_posix(),'authorization_sha256':file_hash(authorization),
        'offline_gate_sha256':file_hash(gates),'fake_fixture':False}
    value['identity']=digest(value);write(output,value);return value


class TestContinuationRuntime(Runtime):
    def __init__(self,*args,policy,**kwargs):
        super().__init__(*args,**kwargs);self.policy=policy;self.recovery_cfg=recovery_config(self.config,policy)

    def complete(self,role,*args,**kwargs):
        if role!='solver' or self.phase!='test':raise Abort('CONTINUATION_TEST_SOLVER_ONLY')
        return super().complete(role,*args,**kwargs)

    def score_prediction(self,prediction,reference):return score(prediction,reference,policy=self.policy)

    def local_worker(self,operation,*,stage,repeat,split,key):
        def record(**event):
            self.event('LOCAL_WORKER_RETRY',phase=self.phase,arm=self.arm,repeat=repeat,split=split,stage=stage,key=key,**event)
            progress(f'LOCAL_WORKER_RETRY stage={stage} phase={self.phase} category={event["category"]} retry={event["retry_index"]}')
        return retry_local_worker(operation,self.recovery_cfg,self.config['local_worker_initial_deadlines_seconds'][self.phase],
            check=self.guard,wait=self.delay,on_retry=record)


def restore_runtime(directory,frozen,policy,models,transport,check):
    rt=TestContinuationRuntime(directory,frozen['config'],models,frozen['identity'],transport,check,policy=policy,open_event=False)
    snapshot=read(directory/'accounting_snapshot.json')
    rt.last_hash=snapshot['last_event_sha256'];rt.physical=snapshot['physical_attempts'];rt.charged=snapshot['charged_tokens']
    rt.successes=snapshot['phase_successful_semantic_responses'];rt.arm_successes=deepcopy(snapshot['phase_successful_responses_by_arm'])
    rt.roles=deepcopy(snapshot['roles']);rt.logical=deepcopy(snapshot['logical_evaluations']);rt.cache_hits=snapshot['cache_hits']
    rt.retry_categories=deepcopy(snapshot['transient_failure_attempts_by_category']);rt.phase='test'
    from .tokens import TokenLedger
    rt.tokens=TokenLedger.replay(directory)
    rt.cache={p.stem:read(p) for p in (directory/'cache').glob('*.json')}
    import json
    rt.imported_test_contexts={(e['arm'],e['key']) for line in (directory/'accounting.jsonl').read_bytes().splitlines()
        for e in [json.loads(line)] if e['kind']=='LOGICAL_SOLVER' and e['phase']=='test'}
    for selection in read(directory/'SEARCH_COMPLETE.json')['selections']:
        rt.registered.add((selection['arm'],selection['repeat_id'],selection['selected_hash']))
    return rt


def finish_test_profile(rt,selection,rows,models,parent_identity):
    """Already counted paid observations are assembled without another logical call."""
    arm=selection['arm'];repeat=selection['repeat_id'];prompt=SystemPrompt.from_dict(selection['selected'])
    keys=[request_key(parent_identity,repeat,prompt,row,models) for row in rows]
    needed=[row for row,key in zip(rows,keys,strict=True)
            if (arm,key) not in rt.imported_test_contexts or key not in rt.cache]
    if needed:rt.evaluate(prompt,needed,repeat,'test','final')
    return [rt.cache[key] for key in keys]


def execute(root,bundle,freeze_path,*,transport_override=None):
    continuation=read(freeze_path);content=dict(continuation);cid=content.pop('identity')
    if digest(content)!=cid:raise ProtocolViolation('CONTINUATION_FREEZE_IDENTITY')
    prep=read(root/continuation['preparation_path']);directory=root/continuation['run_root']
    fake=transport_override is not None
    if fake!=bool(continuation.get('fake_fixture')):raise ProtocolViolation('CONTINUATION_PROVIDER_CLASSIFICATION')
    clients={}
    if not fake:
        preflight(root,bundle)
        if (source_inventory(root)!=continuation['source_inventory'] or load_policy(root,policy_version(continuation['policy']))!=continuation['policy']
            or validate_bundle(bundle)['bundle_hash']!=continuation['bundle_hash']
            or file_hash(root/continuation['preparation_path'])!=continuation['preparation_sha256']
            or file_hash(root/continuation['authorization_path'])!=continuation['authorization_sha256']):
            raise ProtocolViolation('CONTINUATION_STARTUP_IDENTITY')
        check=SourceGuard(root,continuation)
        if inventory(root/prep['parent'])!=prep['parent_inventory'] or inventory(directory)!=prep['prepared_inventory']:
            raise ProtocolViolation('CONTINUATION_IMPORTED_EVIDENCE_CHANGED')
        marker=root/'runs/single_prompt_continuation_consumed'/f'{continuation["authorization_sha256"]}.json'
        if marker.exists():raise ProtocolViolation('CONTINUATION_AUTHORIZATION_CONSUMED')
        models=read(bundle/'model_contract.json')
        transport,clients=real_transport(root,{**models,'routes':{'solver':models['routes']['solver']}})
        marker.parent.mkdir(parents=True,exist_ok=True)
        with marker.open('xb') as stream:stream.write((cid+'\n').encode())
    else:check=lambda:None;transport=transport_override
    write(directory/'continuation_frozen.json',continuation)
    frozen=read(directory/'frozen.json');models=read(bundle/'model_contract.json')
    rt=restore_runtime(directory,frozen,continuation['policy'],models,transport,check)
    seal_hash=file_hash(directory/'SEARCH_COMPLETE.json');audit_hash=file_hash(directory/'search_audit.json')
    def release():
        if file_hash(directory/'SEARCH_COMPLETE.json')!=seal_hash or file_hash(directory/'search_audit.json')!=audit_hash:
            raise Abort('CONTINUATION_SELECTION_SEAL_CHANGED')
        original_seal=read(directory/'SEARCH_COMPLETE.json')
        if original_seal.get('posthoc_content_sha256')!=file_hash(directory/'posthoc_content.json'):
            raise Abort('CONTINUATION_POSTHOC_SEAL_CHANGED')
    rt.test_release_check=release
    rt.event('CONTINUATION_OPEN',continuation_identity=cid)
    write(directory/'accounting_snapshot.json',rt.snapshot())
    write(directory/'lifecycle.json',{'status':'RUNNING','phase':'test','attempt_identity':frozen['identity'],
        'continuation_identity':cid,'fake_provider':fake})
    started=time.monotonic();selections=read(directory/'SEARCH_COMPLETE.json')['selections'];results=[]
    try:
        rows=load_rows(bundle,'test','test')
        for selection in selections:
            check();release();folder=directory/selection['arm']/f'repeat_{selection["repeat_id"]}'
            if (folder/'test_result.json').exists():
                results.append(read(folder/'test_result.json'));continue
            rt.bind_arm(selection['arm']);prompt=SystemPrompt.from_dict(selection['selected'])
            test_started=time.monotonic()
            profile=finish_test_profile(rt,selection,rows,models,frozen['identity'])
            record=test_record(selection,profile);write(folder/'test_predictions.json',profile);write(folder/'test_result.json',record)
            write(folder/'test_accounting.json',{'arm':selection['arm'],'repeat_id':selection['repeat_id'],
                'wall_seconds':time.monotonic()-test_started,'wall_scope':'continuation only; imported partial Test time unavailable',
                'tokens':rt.token_snapshot(selection['repeat_id'])})
            results.append(record)
            progress(f'TEST_REPEAT_COMPLETE arm={selection["arm"]} repeat={selection["repeat_id"]} correct={record["correct"]}/300')
        write(directory/'accounting_snapshot.json',rt.snapshot());check()
        final=reconcile(directory,bundle,include_test=True,check=check,
            scoring_function=partial(score,policy=continuation['policy']),recovery_policy_config=rt.recovery_cfg,
            terminal_repair_policy=continuation['policy'] if policy_version(continuation['policy'])=='v7' else None)
        write(directory/'final_audit.json',final)
        result={'status':'EXECUTION_COMPLETE','attempt_identity':frozen['identity'],'continuation_identity':cid,
            'fake_provider':fake,'scientific_status':'FAKE_ENGINEERING_FIXTURE' if fake else 'AUDITED_COMPLETE_WITH_'+policy_version(continuation['policy']).upper()+'_SCORING_AMENDMENT',
            'selections':selections,'test_results':results,'accounting':rt.snapshot(),'wall_seconds':time.monotonic()-started,
            'final_audit_sha256':file_hash(directory/'final_audit.json'),'original_accounting':prep['original_accounting'],
            'additional_physical_attempts':rt.physical-prep['original_accounting']['physical_attempts'],
            'additional_charged_tokens':rt.charged-prep['original_accounting']['charged_tokens']}
        from .analysis import paired,align_tokens
        profiles={(s['arm'],s['repeat_id']):read(directory/s['arm']/f'repeat_{s["repeat_id"]}'/'test_predictions.json') for s in selections}
        result.update(test_contract=frozen.get('test_contract'),paired_analysis=paired(profiles),
            token_accounting=rt.tokens.view(),
            token_accounting_by_arm={arm:rt.tokens.view(arm=arm) for arm in frozen['config']['arms']},
            test_accounting=[read(directory/s['arm']/f'repeat_{s["repeat_id"]}'/'test_accounting.json') for s in selections],
            search_token_alignment=align_tokens({f'{s["arm"]}:{s["repeat_id"]}':read(directory/s['arm']/f'repeat_{s["repeat_id"]}'/'mechanism_events.json') for s in selections}),
            posthoc_review=read(directory/'posthoc_content.json'))
        write(directory/'compute_accounting.json',rt.tokens.view())
        write(directory/'completion.json',result)
        write(directory/'lifecycle.json',{'status':'EXECUTION_COMPLETE','phase':'complete','continuation_identity':cid,'fake_provider':fake})
        return result
    except BaseException as exc:
        rt.failed.set();write(directory/'accounting_snapshot.json',rt.snapshot())
        record={'status':'EXECUTION_ABORTED','category':str(exc) if isinstance(exc,(Abort,ProtocolViolation)) else type(exc).__name__,
            'continuation_identity':cid,'fake_provider':fake,'automatic_rerun_authorized':False,'accounting':rt.snapshot()}
        write(directory/'completion.json',record);write(directory/'lifecycle.json',record);raise
    finally:
        for client in clients.values():client.close()


def publish(root,directory,output):
    result=read(directory/'completion.json');continuation=read(directory/'continuation_frozen.json');audit=read(directory/'final_audit.json')
    if (result['status']!='EXECUTION_COMPLETE' or result['fake_provider'] or output.exists()
        or audit['status']!='PASS' or audit.get('incomplete_test_preparation_only')
        or file_hash(directory/'final_audit.json')!=result['final_audit_sha256']):
        raise ProtocolViolation('REAL_COMPLETED_CONTINUATION_REQUIRED')
    summary=build_summary(result,read(directory/'frozen.json'),audit)
    summary.update(identity='GEPA_TWO_ARM_SINGLE_PROMPT_MATH_'+policy_version(continuation['policy']).upper()+'_CONTINUATION_REPORT',source_sha=continuation['source_sha'],
        continuation_identity=continuation['identity'],scoring_policy_sha256=digest(continuation['policy']),
        parent_source_sha=read(directory/'frozen.json')['source_sha'],
        scoring_amendment='bounded exact separation; pinned fallback; finite unresolved-computation escalation',
        additional_physical_attempts=result['additional_physical_attempts'],additional_charged_tokens=result['additional_charged_tokens'],
        existing_score_changes_before_provider_access=0,search_rerun=False,
        wall_seconds_scope='continuation_only; original source execution and stall excluded',
        test_exposure='repair motivated by an exposed sealed Test computation; no fresh confirmatory claim')
    write(output/'summary.json',summary);write(output/'integrity_audit.json',audit)
    from ..audit import require_clean_public_artifacts
    require_clean_public_artifacts([output])
    return summary
