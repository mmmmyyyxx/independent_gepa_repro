"""Governed owner execution: fresh freeze, one-shot authorization, no resume."""
from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path
import sys
from typing import Any

from ..audit import audit_value
from ..protocol import ProtocolViolation
from ..versions import GEPA_COMMIT
from .benchmark import require_reference
from .contract import PINS,digest,file_hash,git,read,write,source_inventory,validate_bundle,load_config
from .evaluation import audit_selected
from .reporting import build_report
from .runtime import Runtime,real_transport,audit_accounting,ExecutionAbort
from .search import run_window,REFLECTION_TEMPLATE
from .candidate_guard import GUARD_ID
from .conformance import await_owner_review,verify_final_release

def require_fresh_user_grant(root: Path,task_sha: str) -> None:
    """A source repair or new experiment identity never renews a one-shot grant."""
    directory=root/'runs/authorization_consumed'
    if (directory/f'user_grant_{task_sha}.json').exists():
        raise ProtocolViolation('USER_API_GRANT_ALREADY_CONSUMED')
    # Reconcile historical attempts created before the grant-keyed marker existed.
    for path in (root/'runs').glob('*/frozen_attempt.json'):
        prior=read(path)
        if prior.get('user_task_sha256')==task_sha and (directory/f'{prior.get("identity")}.json').exists():
            raise ProtocolViolation('USER_API_GRANT_ALREADY_CONSUMED')

def verify_environment(root: Path) -> dict[str,str]:
    from .._vendor import import_vendor_gepa,vendor_gepa_src
    vendor=root/'vendor/gepa'
    if git(vendor,'rev-parse','HEAD')!=GEPA_COMMIT or git(vendor,'status','--short'):
        raise ProtocolViolation('GEPA_PIN_OR_WORKTREE_MISMATCH')
    if vendor_gepa_src() not in Path(import_vendor_gepa().__file__).resolve().parents:
        raise ProtocolViolation('GEPA_IMPORT_MISMATCH')
    pins={**PINS,'openai':'2.37.0'}
    if any(importlib.metadata.version(k)!=v for k,v in pins.items()):
        raise ProtocolViolation('EVALUATOR_OR_PROVIDER_DEPENDENCY_MISMATCH')
    return pins

def validate_models(models: dict[str,Any]) -> None:
    if models['evaluator_pins']!=PINS or models['models']['solver']!='qwen3-8b' or models['models']['optimizer_reflection']!='qwen3.7-flash':
        raise ProtocolViolation('FROZEN_MODEL_MISMATCH')
    solver={'identity':'SOLVER_DECODING_POLICY_V2','enable_thinking':False,'frequency_penalty':0,
            'max_output_tokens':3600,'min_p':0,'presence_penalty':0,'temperature':0.2,'top_k':20,'top_p':0.8}
    if models['solver_decoding_policy']!=solver: raise ProtocolViolation('SOLVER_DECODING_MISMATCH')
    optimizer=models['optimizer_generation_policy']
    expected={'identity':'OPTIMIZER_REFLECTION_GENERATION_POLICY_V3','enable_thinking':False,
        'temperature':0.7,'top_p':0.8,'top_k':20,'presence_penalty':1.5,'frequency_penalty':0,
        'max_completion_tokens':1800,'accounting_output_ceiling':1810}
    if any(optimizer.get(k)!=v for k,v in expected.items()): raise ProtocolViolation('OPTIMIZER_DECODING_MISMATCH')
    if models['invalid_recovery_policy']['max_semantic_attempts']!=4 or models['prediction_validity_policy']['identity']!='MATH_PREDICTION_VALIDITY_V2':
        raise ProtocolViolation('PREDICTION_RECOVERY_MISMATCH')

def preflight(root: Path,bundle: Path,config_path: Path) -> dict[str,Any]:
    config=load_config(config_path); manifest=validate_bundle(bundle); pins=verify_environment(root)
    validate_models(read(bundle/'model_contract.json'))
    for example in read(bundle/'optimize.json'): require_reference(example['reference'])
    old=manifest['historical_ledger_snapshot']
    if old['reserved_inflight']!=0 or old['remaining']<config['token_ceiling']:
        raise ProtocolViolation('PROJECT_BUDGET_PREFLIGHT_FAILED')
    return {'status':'PASS','provider_calls':0,'config_hash':digest(config),'bundle_hash':manifest['bundle_hash'],
        'dependencies':pins,'source_inventory_hash':digest(source_inventory(root)),
        'reflection_template_hash':digest(REFLECTION_TEMPLATE),'search_support':60,
        'shadow_calls':0,'validation_calls':0,'test_calls':0}

def freeze(root: Path,bundle: Path,config_path: Path,task: Path,gates: Path,output: Path,
           private: Path,public: Path) -> dict[str,Any]:
    if output.exists() or private.exists() or public.exists(): raise ProtocolViolation('FRESH_FREEZE_AND_OUTPUTS_REQUIRED')
    require_fresh_user_grant(root,file_hash(task))
    if load_config(config_path).get('candidate_guard')!=GUARD_ID:
        raise ProtocolViolation('CURRENT_CANDIDATE_GUARD_ID_REQUIRED')
    if load_config(config_path).get('owner_conformance_policy')!='selected_outcome_blind_before_full_v1':
        raise ProtocolViolation('CURRENT_OWNER_CONFORMANCE_POLICY_REQUIRED')
    if load_config(config_path).get('candidate_review_policy')!='owner_semantic_before_solver_v1':
        raise ProtocolViolation('PRE_SOLVER_CANDIDATE_REVIEW_REQUIRED')
    if load_config(config_path).get('reviewer_identity')!='codex_conformance_v4_seed81_20261008':
        raise ProtocolViolation('FROZEN_INDEPENDENT_REVIEWER_REQUIRED')
    if git(root,'diff','--name-only') or git(root,'diff','--cached','--name-only'):
        raise ProtocolViolation('CLEAN_TRACKED_SOURCE_REQUIRED')
    receipt=preflight(root,bundle,config_path); evidence=read(gates)
    if evidence.get('status')!='PASS' or evidence.get('provider_calls')!=0 or evidence.get('source_inventory_hash')!=receipt['source_inventory_hash']:
        raise ProtocolViolation('MATCHING_OFFLINE_GATES_REQUIRED')
    grant=task.read_text(encoding='utf-8')
    normalized=''.join(grant.lower().split())
    if ('authorizes one bounded real-model independent GEPA comparison' not in grant
        and not ('继续自行完成实验' in grant and '300万tokens' in normalized)
        and not ('授权' in grant and 'v4' in normalized and '300万tokens' in normalized)):
        raise ProtocolViolation('EXPLICIT_USER_API_AUTHORIZATION_REQUIRED')
    value={'schema_version':'math_comparison_frozen_attempt_v1','experiment_id':load_config(config_path)['experiment_id'],
        'source_sha':git(root,'rev-parse','HEAD'),'source_inventory':source_inventory(root),
        'config':load_config(config_path),'bundle_hash':validate_bundle(bundle)['bundle_hash'],
        'dependencies':verify_environment(root),'python_executable_sha256':file_hash(Path(sys.executable)),
        'user_task_sha256':file_hash(task),'single_use':True,'authorization_source':'explicit_user_task_text',
        'api_scope':{'roles':['solver','reflection'],'phase':'seven_search_windows_then_frozen_full_audit',
                     'heldout':'denied','retry_authorization':False},
        'command':{'script':'scripts/math_a4_comparison.py','mode':'run',
            'bundle':str(bundle.relative_to(root)).replace('\\','/'),
            'config':str(config_path.relative_to(root)).replace('\\','/'),
            'freeze':str(output.relative_to(root)).replace('\\','/'),
            'private_output':str(private.relative_to(root)).replace('\\','/'),
            'public_output':str(public.relative_to(root)).replace('\\','/'),'allow_real_api':True},
        'offline_gate_receipt':evidence,'initial_prompt_hash':'4e6dfb1595690c9487e7dea0deaafa72363cde09f5ce81186f1e4fbdc4205f80',
        'READY_TO_RUN':True}
    value['identity']=digest(value)
    if audit_value(value): raise ProtocolViolation('FREEZE_SANITIZATION_FAILED')
    write(output,value); return value

def execute(root: Path,bundle: Path,config_path: Path,frozen_path: Path,private: Path,public: Path,
            *,allow_real_api: bool=False,transport_override=None) -> dict[str,Any]:
    frozen=read(frozen_path); config=load_config(config_path); manifest=validate_bundle(bundle)
    check=dict(frozen); identity=check.pop('identity')
    if digest(check)!=identity or frozen['source_sha']!=git(root,'rev-parse','HEAD') or frozen['source_inventory']!=source_inventory(root):
        raise ProtocolViolation('FROZEN_SOURCE_MISMATCH')
    if frozen['config']!=config or frozen['bundle_hash']!=manifest['bundle_hash'] or not frozen['READY_TO_RUN']:
        raise ProtocolViolation('FROZEN_EXPERIMENT_MISMATCH')
    if frozen['dependencies']!=verify_environment(root) or frozen['python_executable_sha256']!=file_hash(Path(sys.executable)):
        raise ProtocolViolation('FROZEN_RUNTIME_MISMATCH')
    if private.exists() or public.exists() or not private.resolve().is_relative_to((root/'runs').resolve()):
        raise ProtocolViolation('FRESH_LOCAL_RUN_REQUIRED')
    actual={'script':'scripts/math_a4_comparison.py','mode':'run','bundle':str(bundle.relative_to(root)).replace('\\','/'),
        'config':str(config_path.relative_to(root)).replace('\\','/'),'freeze':str(frozen_path.relative_to(root)).replace('\\','/'),
        'private_output':str(private.relative_to(root)).replace('\\','/'),'public_output':str(public.relative_to(root)).replace('\\','/'),
        'allow_real_api':allow_real_api}
    if transport_override is None and (not allow_real_api or actual!=frozen['command']):
        raise ProtocolViolation('EXACT_AUTHORIZED_COMMAND_REQUIRED')
    models=read(bundle/'model_contract.json'); validate_models(models)
    if transport_override is None:
        if (config.get('candidate_guard')!=GUARD_ID
            or config.get('candidate_review_policy')!='owner_semantic_before_solver_v1'
            or config.get('reflection_contract_context')!='explicit_immutable_single_line_v1'
            or config.get('reviewer_identity')!='codex_conformance_v4_seed81_20261008'
            or config.get('owner_conformance_policy')!='selected_outcome_blind_before_full_v1'):
            raise ProtocolViolation('CURRENT_REAL_EXECUTION_CONFORMANCE_POLICIES_REQUIRED')
        require_fresh_user_grant(root,frozen['user_task_sha256'])
    if transport_override is None:
        transport,client=real_transport(models)
    else: transport=transport_override; client=None
    marker=root/'runs/authorization_consumed'/f'{identity}.json'; marker.parent.mkdir(parents=True,exist_ok=True)
    try:
        if transport_override is None:
            grant_marker=marker.parent/f'user_grant_{frozen["user_task_sha256"]}.json'
            with grant_marker.open('x',encoding='utf-8') as stream:
                stream.write(identity+'\n');stream.flush();os.fsync(stream.fileno())
        with marker.open('x',encoding='utf-8') as stream: stream.write(identity+'\n');stream.flush();os.fsync(stream.fileno())
    except FileExistsError as exc: raise ProtocolViolation('AUTHORIZATION_ALREADY_CONSUMED') from exc
    private.mkdir(parents=True); write(private/'frozen_attempt.json',frozen)
    runtime=Runtime(private,config,models,read(bundle/'shell.json'),identity,transport)
    def verify_live_source():
        if frozen['source_inventory']!=source_inventory(root):
            raise ExecutionAbort('SOURCE_MUTATED_AFTER_FREEZE')
    runtime.source_check=verify_live_source
    selections=[]; examples=read(bundle/'optimize.json')
    try:
        for window,member in enumerate(config['target_schedule']):
            selection=run_window(runtime,examples,config,window,member,private/f'window_{window}')
            selections.append(selection)
            print(f'Search window={window} member={member} proposals={selection["proposal_count"]} '
                  f'metrics={selection["search_metric_count"]} native_best={selection["native_best_score"]:.3f} '
                  f'full_selected={len(selection["selected"])} charged={runtime.charged}',flush=True)
        write(private/'SEARCH_COMPLETE.json',{'identity':identity,'selections':selections,
            'selection_hash':digest(selections),'search_closed_forever':True,'audit_started':False,
            'search_accounting':runtime.snapshot()})
        if config.get('owner_conformance_policy')=='selected_outcome_blind_before_full_v1':
            await_owner_review(private,identity,selections,examples,timeout_seconds=config['owner_review_timeout_seconds'],
                               bundle=bundle,reviewer=config['reviewer_identity'])
            runtime.final_review_check=lambda:verify_final_release(private,identity,selections,config['reviewer_identity'])
        rows,baselines=audit_selected(runtime,bundle,examples,selections,private)
        write(private/'accounting_snapshot.json',runtime.snapshot()); accounting=audit_accounting(private)
        accounting['logical_evaluations']=runtime.logical; accounting['cache_hits']=runtime.cache_hits
        accounting['role_usage']=runtime.role_usage
        accounting['search_accounting']=read(private/'SEARCH_COMPLETE.json')['search_accounting']
        accounting['structural_vote_preflight']={k:frozen['offline_gate_receipt'][k] for k in (
            'historical_unanimous_vote_locked_examples','historical_all_invalid_examples',
            'historical_correctness_unanimous','single_member_vote_gain_upper_bound')}
        write(private/'candidate_metrics.json',rows); write(private/'realization_diagnostics.json',baselines)
        build_report(public,bundle,selections,rows,baselines,accounting,identity,frozen['source_sha'],config=config)
        result={'status':'EXECUTION_COMPLETE','scientific_integrity':'AWAITING_OWNER_AUDIT','accounting':accounting}
        write(private/'completion.json',result);return result
    except BaseException as exc:
        if runtime.reserved:
            amount=runtime.reserved; runtime.charged+=amount; runtime.reserved=0
            runtime.role_usage[runtime.active_role]['charged_tokens']+=amount
            # Interrupted receipt/persistence failures are conservatively sealed.
            runtime.event({'kind':'FAILURE_CHARGE','physical_attempt':runtime.physical,'amount':amount,
                           'role':runtime.active_role,'category':'UNRESOLVED_CONSERVATIVE_CLOSURE'})
        write(private/'accounting_snapshot.json',runtime.snapshot())
        result={'status':'EXECUTION_ABORTED','category':type(exc).__name__,
                'reason':str(exc) if isinstance(exc,ExecutionAbort) else 'ENGINEERING_OR_CONTRACT_FAILURE',
                'completed_search_windows':len(selections),'accounting':runtime.snapshot(),
                'authorization_consumed':True,'automatic_retry_authorized':False}
        write(private/'completion.json',result);public.mkdir(parents=True,exist_ok=True);write(public/'aborted.json',result)
        raise
    finally:
        if client is not None: client.close()
