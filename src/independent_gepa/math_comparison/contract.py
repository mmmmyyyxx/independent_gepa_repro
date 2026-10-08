"""Frozen comparison bundle and source identities, separate from optimizer state."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

from ..bundle import canonical_json
from ..protocol import ProtocolViolation
from ..versions import GEPA_COMMIT

PINS = {'math-verify': '0.6.0', 'latex2sympy2_extended': '1.0.9',
        'sympy': '1.14.0', 'antlr4-python3-runtime': '4.13.2', 'mpmath': '1.3.0'}
SETTINGS = dict(identity='MATH_VERIFY_SETTINGS_V2', strict=True, float_rounding=6,
    numeric_precision=15, parsing_timeout=3, verification_timeout=3, process_deadline=8,
    fallback_mode='no_fallback', extraction_mode='first_match',
    latex_extraction=dict(try_extract_without_anchor=True, boxed_match_priority=50,
        normalization_config=dict(basic_latex=True, units=True, malformed_operators=True,
            nits=True, boxed='all', equations=False)),
    conversion_config=dict(interpret_as_mixed_fractions=True, interpret_simple_eq_as_assignment=False,
        interpret_contains_as_eq=True),
    allow_set_relation_comp='NOT_EXPOSED_BY_PINNED_API; DISJOINT_CONTAINER_TYPES_REQUIRED',
    two_component_parentheses='AMBIGUOUS_REFERENCE_UNSCORABLE_AFTER_NATIVE_PARSE',
    correctness_direction='gold_first_prediction_second',
    object_families=['expression', 'relation', 'tuple', 'matrix', 'finite_set', 'infinite_set'],
    maximum_expression_characters=2048)

def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()

def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path: Path) -> Any:
    return json.loads(path.read_bytes())

def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w',encoding='utf-8',newline='\n') as stream:
        stream.write(canonical_json(value)+'\n');stream.flush();os.fsync(stream.fileno())

def git(root: Path, *args: str) -> str:
    return subprocess.check_output(['git', *args], cwd=root, encoding='utf-8').strip()

def load_config(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding='utf-8'))
    if (value.get('schema_version') != 'independent_gepa_math_comparison_v1'
        or value.get('seed') != 81 or value.get('target_schedule') != [0,1,3,2,4,0,1]
        or value.get('window_state') != 'reset_from_initial'
        or any(value.get(k) != 'denied' for k in ('shadow_access','validation_access','test_access'))
        or value.get('team_commits') is not False or value.get('resume') != 'denied'
        or value.get('concurrency') != 1):
        raise ProtocolViolation('MATH_COMPARISON_CONFIGURATION_MISMATCH')
    expected = {'search_metric_cap_per_window':36, 'proposal_cap_per_window':6,
        'reflection_minibatch_size':3, 'native_validation_size':6, 'full_candidates_per_window':4,
        'token_ceiling':3_000_000, 'physical_attempt_ceiling':9000}
    if any(type(value.get(k)) is not int or value[k] != v for k,v in expected.items()):
        raise ProtocolViolation('MATH_COMPARISON_BUDGET_MISMATCH')
    if value.get('candidate_selection') != 'native_best_then_native_pareto_then_hash_order_evaluated_proposals':
        raise ProtocolViolation('MATH_COMPARISON_SELECTION_MISMATCH')
    if value.get('provider_profile') != 'lwj' or value.get('cache_policy') != 'window_member_attempt_exact_resolved_request':
        raise ProtocolViolation('MATH_COMPARISON_PROVIDER_MISMATCH')
    if 'candidate_guard' in value:
        from .candidate_guard import GUARD_ID
        if value['candidate_guard'] not in {'math_candidate_conformance_guard_v2','math_candidate_conformance_guard_v3',GUARD_ID}:
            raise ProtocolViolation('CANDIDATE_GUARD_ID_MISMATCH')
    if value.get('owner_conformance_policy') is not None:
        if value['owner_conformance_policy']!='selected_outcome_blind_before_full_v1' or value.get('owner_review_timeout_seconds')!=900:
            raise ProtocolViolation('OWNER_CONFORMANCE_POLICY_MISMATCH')
    if value.get('candidate_review_policy') is not None:
        if (value['candidate_review_policy']!='owner_semantic_before_solver_v1'
            or value.get('owner_review_timeout_seconds')!=900
            or value.get('reflection_contract_context')!='explicit_immutable_single_line_v1'):
            raise ProtocolViolation('CANDIDATE_REVIEW_POLICY_MISMATCH')
        if value.get('candidate_guard')=='math_candidate_conformance_guard_v4' and value.get('reviewer_identity')!='codex_conformance_v4_seed81_20261008':
            raise ProtocolViolation('V4_REVIEWER_IDENTITY_REQUIRED')
    return value

def source_inventory(root: Path) -> dict[str,str]:
    paths = sorted([*root.joinpath('src').rglob('*.py'), *root.joinpath('scripts').glob('*.py'),
                    *root.joinpath('tests').rglob('*.py'), root/'AGENTS.md', root/'pyproject.toml',
                    root/'configs/math_a4_matched.yaml', root/'docs/math_a4_comparison_v1.md',
                    root/'configs/math_a4_matched_guard_repair.yaml', root/'docs/math_a4_copy_guard_repair_v1.md',
                    root/'configs/math_a4_matched_guard_repair_v3.yaml',root/'docs/math_a4_guarded_comparison_v3.md',
                    root/'configs/math_a4_matched_guard_repair_v4.yaml',root/'docs/math_a4_guarded_comparison_v4.md'])
    return {str(p.relative_to(root)).replace('\\','/'):file_hash(p) for p in paths}

def export_bundle(source: Path, destination: Path) -> str:
    """One-time read-only export. Parse only the sixty frozen Optimize records."""
    if destination.exists():
        raise ProtocolViolation('FRESH_COMPARISON_BUNDLE_REQUIRED')
    binding_path = source/'experiments/execution_bindings/math_v2_2_gradient_pattern_seed81_pilot_v2.json'
    binding = read(binding_path)
    paths = {'binding.json':binding_path,
        'parent_manifest.yaml':source/'experiments/manifests/math_v2_2_gradient_pattern_seed81_pilot_v2.yaml',
        'subsets.json':source/binding['low_cost_subsets_path'],
        'split_manifest.json':source/binding['split_directory']/'math.json',
        'canonical_manifest.json':source/binding['canonical_root']/'manifests/math.json',
        'initial_team.json':source/binding['initial_team_path'],
        'settings.json':source/binding['verify_settings_path']}
    for name, key in [('subsets.json','low_cost_subsets_sha256'),('split_manifest.json','split_manifest_sha256'),
                      ('canonical_manifest.json','canonical_manifest_sha256'),
                      ('initial_team.json','initial_team_artifact_sha256')]:
        if file_hash(paths[name]) != binding[key]: raise ProtocolViolation('A4_PARENT_HASH_MISMATCH')
    # The executed binding identifies settings by canonical JSON, not its newline-bearing file bytes.
    if digest(read(paths['settings.json']))!=binding['verify_settings_sha256']:
        raise ProtocolViolation('A4_SETTINGS_IDENTITY_MISMATCH')
    memberships = read(paths['subsets.json'])['memberships']['pilot_optimize']
    if len(memberships) != 60 or digest([r['stable_example_id'] for r in memberships]) != binding['low_cost_protocol']['membership_hashes']['pilot_optimize']:
        raise ProtocolViolation('OPTIMIZE60_MEMBERSHIP_MISMATCH')
    canonical = read(paths['canonical_manifest.json'])
    raw = source/binding['canonical_root']/'raw/math/train.jsonl'
    expected_raw = next(r['canonical_sha256'] for r in canonical['source']['canonical_sources'] if r['name']=='train')
    if file_hash(raw) != expected_raw: raise ProtocolViolation('MATH_SOURCE_HASH_MISMATCH')
    wanted = {r['source_index']:r for r in memberships}; records = {}
    with raw.open('rb') as stream:
        for index,line in enumerate(stream):
            if index not in wanted: continue
            row = json.loads(line); expected = wanted[index]
            if any(row[k]!=expected[k] for k in ('stable_example_id','input_sha256','content_sha256')):
                raise ProtocolViolation('OPTIMIZE_SOURCE_ROW_MISMATCH')
            records[row['stable_example_id']] = {'example_id':row['stable_example_id'],
                'problem':row['content']['problem'], 'reference':row['reference_final_answer'],
                'input_sha256':row['input_sha256'], 'content_sha256':row['content_sha256']}
    examples = [records[r['stable_example_id']] for r in memberships]
    team = read(paths['initial_team.json'])
    if len(team['members'])!=5 or any(m['prompt']!='Solve the problem.' for m in team['members']):
        raise ProtocolViolation('INITIAL_TEAM_MISMATCH')
    # Export immutable format strings from assignments, without importing sibling code.
    import ast
    interface_path = source/'multi_dataset_diverse_rl/benchmarks/math_v21_interface.py'
    assignments = {}
    for node in ast.parse(interface_path.read_text(encoding='utf-8')).body:
        if isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant):
            assignments.update({t.id:node.value.value for t in node.targets if isinstance(t,ast.Name)})
    shell = {'system':assignments['MATH_SOLVER_INTERFACE_V3'], 'suffix':assignments['MATH_SOLVER_INTERFACE_V4_USER_SUFFIX']}
    if hashlib.sha256((shell['system']+shell['suffix']).encode()).hexdigest()!=binding['solver_output_interface']['sha256']:
        raise ProtocolViolation('SOLVER_SHELL_MISMATCH')
    destination.mkdir(parents=True)
    write(destination/'optimize.json',examples); write(destination/'shell.json',shell)
    write(destination/'model_contract.json',{k:binding[k] for k in ('models','solver_decoding_policy',
        'optimizer_generation_policy','decoding','invalid_recovery_policy','prediction_validity_policy',
        'solver_output_interface','evaluator_pins')})
    write(destination/'settings.json',read(paths['settings.json']))
    # Historical outputs are audit-only data and never accessible to the search adapter.
    initial_path = source/'runs/math_v2_2_gradient_pattern_A4_seed81_pilot_attempt2/initial_state_private.json'
    state = read(initial_path)
    if [r['question_hash'] for r in state['diagnostics']['team_states']] != [r['example_id'] for r in examples]:
        raise ProtocolViolation('INITIAL_PEER_SUPPORT_MISMATCH')
    write(destination/'audit_only/initial.json',{'profiles':state['diagnostics']['raw_profiles'],
        'correctness':[r['team_correctness'] for r in state['diagnostics']['team_states']],
        'vote':[r['vote_correct'] for r in state['diagnostics']['team_states']],
        'state_id':state['team_state_id']})
    report = source/'reports/math_v2_2_gradient_pattern_seed81_pilot_v2_execution_20261008'
    write(destination/'audit_only/a4_summary.json',read(report/'summary.json'))
    write(destination/'audit_only/a4_full.json',read(report/'full_outcomes.json'))
    lineages=[];lineage_hashes={}
    for path in sorted(initial_path.parent.glob('layer1_*.lineage.jsonl')):
        rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        if len(rows)!=6 or max(r.get('generation',0) for r in rows)!=6: continue
        evaluated=[r for r in rows if r.get('solver_evaluated')]
        panels={tuple(r['local_examples_evaluated']) for r in evaluated}
        if len(panels)!=1: raise ProtocolViolation('A4_LOCAL_PANEL_IDENTITY_MISMATCH')
        panel=next(iter(panels))
        lineages.append({'target_member':rows[0]['target_member'],'generation_count':6,'root_metrics':len(panel),
            'child_metrics':sum(len(r['local_examples_evaluated']) for r in evaluated),
            'logical_local_metrics':len(panel)+sum(len(r['local_examples_evaluated']) for r in evaluated)})
        lineage_hashes[path.name]=file_hash(path)
    if len(lineages)!=7: raise ProtocolViolation('A4_SEVEN_COMPLETE_LOCAL_WINDOWS_REQUIRED')
    write(destination/'audit_only/a4_local_budget.json',{'windows':lineages,
        'logical_local_metrics':sum(r['logical_local_metrics'] for r in lineages),
        'source_lineage_hashes':lineage_hashes,'root_once_verified_source_hash':file_hash(source/'multi_dataset_diverse_rl/search/bounded_layer1.py')})
    ledger_path = source/'runs/math_autonomous_accounting_v2/token_ledger/AUTONOMOUS_REAL_TOKEN_LEDGER_V2.json'
    ledger = read(ledger_path)
    manifest = {'schema_version':'math_comparison_bundle_v1','gepa_commit':GEPA_COMMIT,
        'source_repository_commit':git(source,'rev-parse','HEAD'),
        'a4_execution_commit':read(report/'provenance.json')['source_sha'],
        'dataset_identity':binding['canonical_manifest_sha256'], 'split_identity':binding['split_manifest_sha256'],
        'optimize_membership_hash':binding['low_cost_protocol']['membership_hashes']['pilot_optimize'],
        'source_file_hashes':{name:file_hash(p) for name,p in paths.items()},
        'audit_initial_source_sha256':file_hash(initial_path),
        'historical_ledger_snapshot':{k:ledger[k] for k in ('charged_total','remaining','reserved_inflight','last_event_sha256')},
        'historical_authorization_reused':False,
        'files':{str(p.relative_to(destination)).replace('\\','/'):file_hash(p) for p in destination.rglob('*.json')}}
    manifest['bundle_hash']=digest(manifest); write(destination/'manifest.json',manifest)
    validate_bundle(destination)
    return manifest['bundle_hash']

def validate_bundle(root: Path) -> dict[str,Any]:
    manifest = read(root/'manifest.json'); check = dict(manifest); identity = check.pop('bundle_hash')
    if digest(check)!=identity or manifest['gepa_commit']!=GEPA_COMMIT:
        raise ProtocolViolation('MATH_BUNDLE_IDENTITY_MISMATCH')
    for name,identity in manifest['files'].items():
        path = (root/name).resolve()
        if not path.is_relative_to(root.resolve()) or file_hash(path)!=identity:
            raise ProtocolViolation('MATH_BUNDLE_FILE_MISMATCH')
    examples = read(root/'optimize.json')
    if (len(examples)!=60 or len({r['example_id'] for r in examples})!=60
        or digest([r['example_id'] for r in examples])!=manifest['optimize_membership_hash']
        or read(root/'settings.json')!=SETTINGS):
        raise ProtocolViolation('MATH_BUNDLE_DATA_MISMATCH')
    return manifest
