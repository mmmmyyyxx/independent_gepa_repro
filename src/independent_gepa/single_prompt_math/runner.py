"""Freeze, execute once, audit before Test, and publish aggregate evidence."""
from __future__ import annotations

from collections import Counter
import importlib.metadata
from pathlib import Path
import statistics
import time
import yaml

from ..protocol import ProtocolViolation
from ..versions import GEPA_COMMIT
from .common import Abort,digest,file_hash,read,write,git,source_inventory,require_private,progress
from .bundle import validate_bundle,load_rows
from .prompt import SystemPrompt
from .runtime import Runtime,real_transport
from .search import run_repeat
from .audit import reconcile

CONFIG='configs/gepa_single_prompt_math_seed42_repeat3.yaml'
PROTOCOL='docs/gepa_single_prompt_math_v1.md'


def load_config(root: Path):
    cfg=yaml.safe_load((root/CONFIG).read_text(encoding='utf-8'))
    expected={'schema_version':'gepa_single_prompt_two_arm_math_v4','seed':42,'repeat_ids':[1,2,3],
        'arms':['strict_validation','native_pareto'],'cell_order':'arm_then_repeat_sequential',
        'max_native_iterations':20,'selectors':{'strict_validation':'current_best','native_pareto':'pareto'},'frontier_type':'instance',
        'module_selector':'round_robin','reflection_minibatch_size':3,'skip_perfect_score':True,
        'use_merge':False,'cache_evaluation':False,'val_evaluation_policy':'full_eval',
        'mutable_components':['role','strategy','answer'],'maximum_rendered_prompt_characters':None,'candidate_guard_policy':'native_only',
        'solver_concurrency':32,'test_solver_concurrency':16,'reflection_concurrency':1,
        'training_successful_semantic_and_inflight_ceiling':90420,'test_successful_semantic_and_inflight_ceiling':3600,
        'token_ceiling':None,'network_failed_physical_attempt_ceiling':None,
        'network_retry_categories':['APITimeoutError','APIConnectionError','APIStatusError_transient','TransientProviderPayload'],
        'http_retry_status_codes':[408,409,425,429],'http_retry_status_range':[500,599],
        'provider_retry_limit':None,'retry_after_policy':'max_backoff_and_valid_seconds_ms_http_date',
        'provider_cooldown':'shared_provider_profile','recovery_wait_heartbeat_seconds':30,
        'local_worker_retry_categories':['MATH_EVALUATOR_TIMEOUT','MATH_EVALUATOR_RESOURCE_TEMPORARY'],
        'local_worker_retry_limit':None,'local_worker_initial_deadlines_seconds':{'search':8,'test':30},
        'local_worker_retry_deadline_multiplier':2,'local_worker_retry_max_deadline_seconds':120,'network_backoff_seconds':[2,4,8,16,30,60],
        'reflection_truncation_draws':4,'solver_semantic_draws':4,'test_worker_deadline_seconds':30,
        'cache_policy':'exact_resolved_solver_same_repeat_across_arms_phase_split_request',
        'teacher_cache':'forbidden','validation_access':'native_selection_only_no_reflection_feedback',
        'test_access':'after_all_six_searches_audited_and_frozen','shadow_access':'denied',
        'resume':'denied','automatic_rerun':'denied','provider_fallback':False}
    if any(cfg.get(k)!=v or type(cfg.get(k)) is not type(v) for k,v in expected.items()):
        raise ProtocolViolation('SINGLE_PROMPT_CONFIGURATION_MISMATCH')
    if set(cfg)!=set(expected)|{'experiment_id'}:raise ProtocolViolation('UNREAD_CONFIGURATION_FIELD')
    return cfg


def preflight(root: Path,bundle: Path):
    cfg=load_config(root);data=validate_bundle(bundle)
    import gepa
    if (git(root/'vendor/gepa','rev-parse','HEAD')!=GEPA_COMMIT or git(root/'vendor/gepa','status','--porcelain')
        or not Path(gepa.__file__).resolve().is_relative_to((root/'vendor/gepa').resolve())):
        raise ProtocolViolation('PINNED_NATIVE_GEPA_REQUIRED')
    from ..math_comparison.contract import PINS
    for name,version in {**PINS,'openai':'2.37.0'}.items():
        if importlib.metadata.version(name)!=version:raise ProtocolViolation('PINNED_DEPENDENCY_MISMATCH')
    train=load_rows(bundle,'optimize','search');validation=load_rows(bundle,'validation','search')
    if set(r['stable_example_id'] for r in train)&set(r['stable_example_id'] for r in validation):
        raise ProtocolViolation('SEARCH_VALIDATION_MEMBERSHIP_OVERLAP')
    models=read(bundle/'model_contract.json')
    if (models['routes']['solver']['model']!='gpt-4o-mini' or models['routes']['solver']['provider_profile']!='openlux'
        or models['routes']['reflection']['model']!='qwen3.7-flash' or models['routes']['reflection']['provider_profile']!='lwj'):
        raise ProtocolViolation('REFERENCE_MODEL_ROUTING_MISMATCH')
    return {'identity':'SINGLE_PROMPT_GEPA_PREFLIGHT_V4','status':'PASS','READY_TO_RUN':False,
        'config_sha256':file_hash(root/CONFIG),'protocol_sha256':file_hash(root/PROTOCOL),
        'source_inventory_sha256':digest(source_inventory(root)),'bundle_hash':data['bundle_hash'],
        'seed':42,'repeat_ids':cfg['repeat_ids'],'arms':cfg['arms'],'counts':data['counts'],
        'provider_calls':0,'source_freeze_required':True}


class SourceGuard:
    def __init__(self,root,frozen):
        self.root=root;self.frozen=frozen
        if git(root,'rev-parse','HEAD')!=frozen['source_sha']:raise ProtocolViolation('FROZEN_SOURCE_HEAD_MISMATCH')
        if source_inventory(root)!=frozen['source_inventory']:raise ProtocolViolation('FROZEN_SOURCE_INVENTORY_MISMATCH')
        self.stamps={p:((root/p).stat().st_mtime_ns,(root/p).stat().st_size) for p in frozen['source_inventory']}
        self.gitdir=Path(git(root,'rev-parse','--absolute-git-dir'))
        common=Path(git(root,'rev-parse','--git-common-dir'))
        self.common_gitdir=common.resolve() if common.is_absolute() else (root/common).resolve()
        self.frozen_head_text=(self.gitdir/'HEAD').read_text().strip()

    def current_head_sha(self):
        head=(self.gitdir/'HEAD').read_text().strip()
        if head!=self.frozen_head_text:raise Abort('FROZEN_SOURCE_HEAD_CHANGED')
        if not head.startswith('ref: '):return head
        reference=head.removeprefix('ref: ')
        try:return (self.common_gitdir/reference).read_text().strip()
        except FileNotFoundError:
            # git pack-refs can remove a loose ref without changing the commit.
            packed=self.common_gitdir/'packed-refs'
            if packed.exists():
                for line in packed.read_text().splitlines():
                    fields=line.split()
                    if len(fields)==2 and fields[1]==reference:return fields[0]
            raise Abort('FROZEN_SOURCE_HEAD_UNAVAILABLE')

    def __call__(self):
        for path,stamp in list(self.stamps.items()):
            value=(self.root/path).stat();current=(value.st_mtime_ns,value.st_size)
            if current!=stamp:
                # A touch, antivirus scan or identical save does not alter frozen bytes.
                if file_hash(self.root/path)!=self.frozen['source_inventory'][path]:raise Abort('FROZEN_SOURCE_CHANGED')
                self.stamps[path]=current
        if self.current_head_sha()!=self.frozen['source_sha']:raise Abort('FROZEN_SOURCE_HEAD_CHANGED')


def freeze(root,bundle,authorization,gates,output,run_root):
    receipt=preflight(root,bundle);evidence=read(gates);cfg=load_config(root)
    if (evidence.get('status')!='PASS' or evidence.get('source_inventory_sha256')!=receipt['source_inventory_sha256']
        or evidence.get('complete_two_arm_three_repeat_fake_e2e')!='PASS'):
        raise ProtocolViolation('COMPLETE_CURRENT_OFFLINE_GATES_REQUIRED')
    if git(root,'diff','--name-only') or git(root,'diff','--cached','--name-only'):
        raise ProtocolViolation('COMMITTED_CLEAN_SOURCE_REQUIRED')
    inventory=source_inventory(root);tracked=set(git(root,'ls-files').splitlines())
    if set(inventory)-tracked:raise ProtocolViolation('UNCOMMITTED_EXPERIMENT_SOURCE')
    run_root=require_private(root,run_root)
    if run_root.exists() or output.exists():raise ProtocolViolation('FRESH_ATTEMPT_PATHS_REQUIRED')
    auth=read(authorization)
    if (auth.get('identity')!='USER_REQUESTED_SINGLE_PROMPT_GEPA_SCOPE_V1' or auth.get('execute') is not True
        or auth.get('authorization_stage')!='POST_SEMANTIC_REVIEW_EXACT_FORMAL_APPROVAL'
        or auth.get('source_sha')!=git(root,'rev-parse','HEAD')
        or auth.get('source_inventory_sha256')!=receipt['source_inventory_sha256']
        or auth.get('protocol_sha256')!=receipt['protocol_sha256']
        or auth.get('offline_gate_sha256')!=file_hash(gates)
        or auth.get('config_sha256')!=file_hash(root/CONFIG) or auth.get('bundle_hash')!=receipt['bundle_hash']
        or auth.get('run_root')!=run_root.relative_to(root).as_posix()
        or not auth.get('user_requests') or auth.get('clarifications')!={
            'data':'keep_reference_memberships','arms':['strict_validation','native_pareto'],
            'strict_parent':'single_retained_chain','solver_cache':'share_exact_requests_within_repeat_across_arms',
            'resources':'reference_per_arm_uncapped_tokens','seed':42,
            'candidate_guard':'native_only_no_extra_content_length_nonempty_or_noop_filters'}):
        raise ProtocolViolation('EXACT_NEW_USER_SCOPE_REQUIRED')
    value={'schema_version':'gepa_two_arm_single_prompt_frozen_v4','source_sha':git(root,'rev-parse','HEAD'),
        'source_inventory':inventory,'config':cfg,'config_sha256':file_hash(root/CONFIG),
        'protocol_sha256':file_hash(root/PROTOCOL),'bundle_hash':receipt['bundle_hash'],
        'authorization_sha256':file_hash(authorization),'authorization_path':authorization.relative_to(root).as_posix(),
        'offline_gate_sha256':file_hash(gates),'run_root':run_root.relative_to(root).as_posix(),
        'user_scope_roles':{'search':['solver','reflection'],'test':['solver']},'fake_only_fixture':False}
    value['identity']=digest(value);write(output,value)
    return value


def release_check(run,identity,selections,receipt_sha,seal_sha):
    if (file_hash(run/'search_audit.json')!=receipt_sha or file_hash(run/'SEARCH_COMPLETE.json')!=seal_sha
        or read(run/'SEARCH_COMPLETE.json')['selections']!=selections
        or read(run/'search_audit.json').get('attempt_identity')!=identity
        or read(run/'search_audit.json').get('status')!='PASS'):
        raise Abort('FROZEN_SELECTION_OR_PRETEST_AUDIT_CHANGED')


def execute(root,bundle,frozen_path,run_root,*,transport_override=None):
    frozen=read(frozen_path);check=dict(frozen);identity=check.pop('identity')
    if digest(check)!=identity or validate_bundle(bundle)['bundle_hash']!=frozen['bundle_hash']:
        raise ProtocolViolation('FROZEN_ATTEMPT_OR_BUNDLE_IDENTITY')
    run_root=run_root.resolve()
    if run_root.exists():raise ProtocolViolation('EXISTING_ATTEMPT_NO_RESUME')
    clients={};fake=transport_override is not None
    if not fake:
        preflight(root,bundle)
        require_private(root,run_root)
        if frozen.get('fake_only_fixture') or run_root.relative_to(root).as_posix()!=frozen['run_root']:
            raise ProtocolViolation('FROZEN_EXECUTION_PATH_OR_CLASSIFICATION')
        if load_config(root)!=frozen['config']:raise ProtocolViolation('FROZEN_CONFIGURATION_CHANGED')
        source_check=SourceGuard(root,frozen)
        auth=root/frozen['authorization_path']
        if file_hash(auth)!=frozen['authorization_sha256']:raise ProtocolViolation('FROZEN_USER_AUTHORIZATION_CHANGED')
        marker=root/'runs/single_prompt_consumed'/f'{frozen["authorization_sha256"]}.json'
        if marker.exists():raise ProtocolViolation('SINGLE_USE_USER_SCOPE_ALREADY_CONSUMED')
        transport,clients=real_transport(root,read(bundle/'model_contract.json'))
        marker.parent.mkdir(parents=True,exist_ok=True)
        with marker.open('xb') as stream:stream.write((identity+'\n').encode())
    else:
        if not frozen.get('fake_only_fixture'):raise ProtocolViolation('EXPLICIT_FAKE_FIXTURE_REQUIRED')
        source_check=lambda:None;transport=transport_override
    run_root.mkdir(parents=True);write(run_root/'frozen.json',frozen)
    runtime=Runtime(run_root,frozen['config'],read(bundle/'model_contract.json'),identity,transport,source_check)
    start=time.monotonic();selections=[]
    write(run_root/'lifecycle.json',{'status':'RUNNING','phase':'search','fake_provider':fake,'attempt_identity':identity})
    try:
        initial=read(bundle/'initial.json');train=load_rows(bundle,'optimize','search');validation=load_rows(bundle,'validation','search')
        for arm in frozen['config']['arms']:
            runtime.bind_arm(arm)
            for repeat in frozen['config']['repeat_ids']:
                source_check();validate_bundle(bundle)
                record=run_repeat(runtime,frozen['config'],initial,train,validation,run_root/arm/f'repeat_{repeat}',repeat)
                selections.append(record)
                write(run_root/'accounting_snapshot.json',runtime.snapshot())
                progress(f'SEARCH_REPEAT_COMPLETE arm={arm} repeat={repeat} selected_hash={record["selected_hash"]}')
        source_check();write(run_root/'accounting_snapshot.json',runtime.snapshot())
        search_audit=reconcile(run_root,bundle,check=source_check);write(run_root/'search_audit.json',search_audit)
        seal={'identity':identity,'selections':selections,'selection_sha256':digest(selections),
              'all_searches_closed':True,'test_opened':False,'search_audit_sha256':file_hash(run_root/'search_audit.json')}
        write(run_root/'SEARCH_COMPLETE.json',seal)
        receipt_sha=file_hash(run_root/'search_audit.json');seal_sha=file_hash(run_root/'SEARCH_COMPLETE.json')
        runtime.test_release_check=lambda:release_check(run_root,identity,selections,receipt_sha,seal_sha)
        runtime.enter_test();test_rows=load_rows(bundle,'test','test');results=[]
        write(run_root/'lifecycle.json',{'status':'RUNNING','phase':'test','fake_provider':fake,'attempt_identity':identity})
        for selected in selections:
            runtime.bind_arm(selected['arm'])
            repeat=selected['repeat_id'];prompt=SystemPrompt.from_dict(selected['selected'])
            profile=runtime.evaluate(prompt,test_rows,repeat,'test','final')
            folder=run_root/selected['arm']/f'repeat_{repeat}';write(folder/'test_predictions.json',profile)
            record={'arm':selected['arm'],'repeat_id':repeat,'seed':42,'selected_hash':prompt.prompt_hash,'correct':sum(p['correct'] for p in profile),
                'count':len(profile),'invalid':sum(not p['valid'] for p in profile)}
            write(folder/'test_result.json',record);results.append(record)
            progress(f'TEST_REPEAT_COMPLETE arm={selected["arm"]} repeat={repeat} correct={record["correct"]}/{record["count"]}')
        write(run_root/'accounting_snapshot.json',runtime.snapshot());source_check()
        final=reconcile(run_root,bundle,include_test=True,check=source_check);write(run_root/'final_audit.json',final)
        completion={'status':'EXECUTION_COMPLETE','attempt_identity':identity,'fake_provider':fake,
                    'scientific_status':'FAKE_ENGINEERING_FIXTURE' if fake else 'AUDITED_COMPLETE',
                    'selections':selections,'test_results':results,'accounting':runtime.snapshot(),
                    'wall_seconds':time.monotonic()-start,'final_audit_sha256':file_hash(run_root/'final_audit.json')}
        write(run_root/'completion.json',completion)
        write(run_root/'lifecycle.json',{'status':'EXECUTION_COMPLETE','phase':'complete','fake_provider':fake,'attempt_identity':identity})
        return completion
    except BaseException as exc:
        runtime.failed.set();write(run_root/'accounting_snapshot.json',runtime.snapshot())
        record={'status':'EXECUTION_ABORTED','attempt_identity':identity,'fake_provider':fake,
                'category':str(exc) if isinstance(exc,Abort) else type(exc).__name__,
                'scientific_status':'NOT_EVALUABLE_PENDING_OWNER_AUDIT','accounting':runtime.snapshot(),
                'wall_seconds':time.monotonic()-start,'automatic_rerun_authorized':False}
        write(run_root/'completion.json',record);write(run_root/'lifecycle.json',record)
        raise
    finally:
        for client in clients.values():client.close()



def build_summary(result,frozen,audit):
    selections=[{k:v for k,v in s.items() if k!='selected'} for s in result['selections']]
    grouped={}
    for arm in frozen['config']['arms']:
        items=[r for r in result['test_results'] if r['arm']==arm]
        values=[r['correct']/r['count'] for r in items]
        if len(items)!=3:raise ProtocolViolation('COMPLETE_THREE_REPEAT_ARM_REQUIRED')
        grouped[arm]={'test_mean_accuracy':statistics.mean(values),
            'test_sample_standard_deviation':statistics.stdev(values),'test_correct_counts':[r['correct'] for r in items]}
    paired=[]
    for repeat in (1,2,3):
        values={r['arm']:r['correct'] for r in result['test_results'] if r['repeat_id']==repeat}
        paired.append({'repeat_id':repeat,'pareto_minus_strict_correct':values['native_pareto']-values['strict_validation']})
    deltas=[r['pareto_minus_strict_correct'] for r in paired]
    return {'identity':'GEPA_TWO_ARM_SINGLE_PROMPT_MATH_REPORT_V4',
        'status':'FAKE_ENGINEERING_FIXTURE' if result['fake_provider'] else 'AUDITED_COMPLETE',
        'attempt_identity':frozen['identity'],'source_sha':frozen.get('source_sha'),
        'bundle_hash':frozen['bundle_hash'],'seed':42,'repeat_ids':[1,2,3],
        'candidate_guard_policy':'native_only','semantic_guard_evaluated':False,
        'selectors':frozen['config']['selectors'],'selections':selections,'test_results':result['test_results'],
        'per_arm':grouped,'paired_test_deltas':paired,
        'pareto_win_tie_loss':{'wins':sum(d>0 for d in deltas),'ties':sum(d==0 for d in deltas),'losses':sum(d<0 for d in deltas)},
        'accounting':result['accounting'],'wall_seconds':result['wall_seconds'],
        'cache_cost_allocation':'first dispatcher pays; paired logical evaluations count in both arms',
        'comparison':'native current_best versus native pareto; same harness; iteration caps do not match compute',
        'heldout_exposure':'historically exposed; no independent confirmatory claim',
        'historical_A_B_C':'descriptive external references only','test_used_for_selection':False,
        'shadow_calls':0,'team_commits':0,'automatic_rerun_authorized':False}


def publish(root,run,public):
    result=read(run/'completion.json');frozen=read(run/'frozen.json')
    if result['status']!='EXECUTION_COMPLETE' or result['fake_provider'] or frozen.get('fake_only_fixture'):
        raise ProtocolViolation('REAL_COMPLETE_RESULT_REQUIRED_FOR_SCIENTIFIC_REPORT')
    if public.exists():raise ProtocolViolation('FRESH_PUBLIC_REPORT_REQUIRED')
    audit=read(run/'final_audit.json')
    if (audit['status']!='PASS' or audit.get('incomplete_test_preparation_only')
        or file_hash(run/'final_audit.json')!=result['final_audit_sha256']):
        raise ProtocolViolation('FINAL_AUDIT_RECEIPT_MISMATCH')
    summary=build_summary(result,frozen,audit)
    write(public/'summary.json',summary);write(public/'integrity_audit.json',audit)
    lines=['# GEPA single-Prompt selector comparison','',
        'Both arms use the same pinned native GEPA engine; only current_best versus pareto parent selection differs.',
        'No reference candidate filter or extra content/length/nonempty/no-op guard runs; native acceptance is not semantic or anti-copy certification.',
        'Three repeats per arm use seed42, identical frozen data and repeat-scoped paired Solver realizations.',
        'Each repeat permits20 native iterations; this does not imply equal physical or logical compute.','',
        '| Arm | Repeat | Initial Optimize | Selected Optimize | Initial Validation | Selected Validation | Test |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for s,t in zip(summary['selections'],result['test_results'],strict=True):
        lines.append(f'| {s["arm"]} | {s["repeat_id"]} | {s["initial_optimize_correct"]}/150 | {s["selected_optimize_correct"]}/150 | {s["initial_validation_correct"]}/100 | {s["validation_correct"]}/100 | {t["correct"]}/300 |')
    lines.extend(['',f'Charged Tokens: {audit["charged_tokens"]:,}; physical requests: {audit["physical_attempts"]:,}; pending:0.',
        'Tokens were uncapped by user choice. Finite per-arm semantic-response ceilings and request accounting remained enforced.',
        'Identical requests share one realization within repeat only; fixed arm order allocates physical cost to the first dispatcher.',
        'Historical Test exposure limits interpretation; this is no independent confirmatory Test. Historical A/B/C are external descriptive references.',
        'No rerun or resume is authorized. Prompts, questions, references and responses remain private.',''])
    (public/'README.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
    from ..audit import audit_public_paths
    if audit_public_paths(list(public.glob('*'))):raise ProtocolViolation('PUBLIC_REPORT_SANITIZATION_FAILED')
    return summary
