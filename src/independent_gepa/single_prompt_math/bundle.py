"""One-time read-only export; runtime never imports or reads the sibling project."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..protocol import ProtocolViolation
from .common import digest,file_hash,read,write,git
from .prompt import SystemPrompt

FILES=('initial.json','optimize.json','validation.json','test.json','model_contract.json','reference.json')


def export_bundle(source: Path,destination: Path) -> dict[str,Any]:
    if destination.exists():raise ProtocolViolation('FRESH_SINGLE_PROMPT_BUNDLE_REQUIRED')
    parent=source/'runs/ablations/pattern_c_only_seed42_repeat3_v7/prep/prep.json'
    scope=read(parent)['scope'];manifest_path=source/'experiments/manifests/single_prompt_pattern_c_only_v7.json'
    manifest=read(manifest_path);data=manifest['data'];split_root=source/data['split_directory']
    split=read(split_root/'math.json');membership=split_root/'math.ids.jsonl'
    canonical_root=source/data['canonical_root']
    if (file_hash(manifest_path)!=scope['manifest_sha256']
        or file_hash(split_root/'math.json')!=data['split_manifest_sha256']
        or file_hash(membership)!=data['membership_sha256']
        or file_hash(canonical_root/'manifests/math.json')!=data['canonical_manifest_sha256']):
        raise ProtocolViolation('REFERENCE_COMPARISON_IDENTITY_MISMATCH')
    ids={'optimize':scope['optimize_sample_ids'],'validation':scope['gate_membership']['sample_ids'],
         'test':scope['test_plan']['sample_ids']}
    for role,n in (('optimize',150),('validation',100),('test',300)):
        if len(ids[role])!=n or len(set(ids[role]))!=n:raise ProtocolViolation('REFERENCE_SPLIT_COUNT_MISMATCH')
    if any(set(ids[a])&set(ids[b]) for a,b in (('optimize','validation'),('optimize','test'),('validation','test'))):
        raise ProtocolViolation('REFERENCE_SPLIT_OVERLAP')
    by_id={r['stable_example_id']:r for r in map(__import__('json').loads,membership.read_bytes().splitlines())}
    wanted={i for values in ids.values() for i in values};rows={}
    for role,values in ids.items():
        if any(by_id[i]['project_split']!=role for i in values):raise ProtocolViolation('REFERENCE_SPLIT_ROLE_MISMATCH')
    source_hashes={}
    for item in split['canonical_sources']:
        path=canonical_root/'raw/math'/f'{item["name"]}.jsonl'
        if file_hash(path)!=item['canonical_sha256']:raise ProtocolViolation('REFERENCE_CANONICAL_SOURCE_HASH')
        source_hashes[item['name']]=item['canonical_sha256']
        indices={by_id[i]['source_index']:by_id[i] for i in wanted if by_id[i]['source_split']==item['name']}
        with path.open('rb') as stream:
            for index,line in enumerate(stream):
                if index not in indices:continue
                row=__import__('json').loads(line);expected=indices[index]
                if (any(row[k]!=expected[k] for k in ('stable_example_id','content_sha256','input_sha256'))
                    or hashlib.sha256(row['reference_final_answer'].encode()).hexdigest()!=expected['reference_sha256']):
                    raise ProtocolViolation('REFERENCE_CANONICAL_ROW_MISMATCH')
                rows[row['stable_example_id']]=row
    if set(rows)!=wanted:raise ProtocolViolation('REFERENCE_CANONICAL_ROWS_MISSING')
    initial_path=source/manifest['initial_prompt_path'];initial=read(initial_path)['members']
    if (file_hash(initial_path)!=manifest['initial_prompt_sha256']
        or SystemPrompt.from_dict(initial[0]['prompt']).prompt_hash!=scope['initial_prompt_sha256']
        or len({digest(m['prompt']) for m in initial})!=1):
        raise ProtocolViolation('REFERENCE_INITIAL_PROMPT_MISMATCH')
    SystemPrompt.from_dict(initial[0]['prompt'])
    runtime=scope['plan']['config']['runtime']
    models={k:runtime[k] for k in ('solver_decoding_policy','optimizer_generation_policy','first_solver_capacity',
        'length_recovery_capacity','solver_semantic_draws','provider_timeout_seconds','optimizer_context_limit','optimizer_input_limit')}
    models['routes']={k:runtime['provider_routing_policy']['routes'][k] for k in ('solver','reflection')}
    reference={'identity':'FROZEN_C_V7_DATA_AND_INTERFACE_REFERENCE_V1','reference_source_sha':git(source,'rev-parse','HEAD'),
        'training_source_sha':scope['source_sha'],'parent_scope_identity':scope['scope_identity'],
        'parent_scope_file_sha256':file_hash(parent),'parent_manifest_sha256':file_hash(manifest_path),
        'split_manifest_sha256':file_hash(split_root/'math.json'),'canonical_source_hashes':source_hashes,
        'original_split_seed':split['split_seed'],'original_validation_membership_seed':runtime['validation_membership_seed'],
        'initial_artifact_sha256':file_hash(initial_path),'counts':{k:len(v) for k,v in ids.items()},
        'membership_hashes':{k:digest(v) for k,v in ids.items()},'original_training_runtime':runtime,
        'heldout_exposure':'historically_exposed; not an independent confirmatory Test'}
    destination.mkdir(parents=True)
    write(destination/'initial.json',initial[0]['prompt']);write(destination/'model_contract.json',models)
    write(destination/'reference.json',reference)
    for role,values in ids.items():write(destination/f'{role}.json',[rows[i] for i in values])
    value={'identity':'SINGLE_PROMPT_MATH_COMPARISON_BUNDLE_V1','counts':reference['counts'],
        'membership_hashes':reference['membership_hashes'],'files':{f:file_hash(destination/f) for f in FILES}}
    value['bundle_hash']=digest(value);write(destination/'manifest.json',value)
    return validate_bundle(destination)


def validate_bundle(bundle: Path) -> dict[str,Any]:
    value=read(bundle/'manifest.json');check=dict(value);sha=check.pop('bundle_hash',None)
    if (value.get('identity')!='SINGLE_PROMPT_MATH_COMPARISON_BUNDLE_V1' or digest(check)!=sha
        or set(value['files'])!=set(FILES) or any(file_hash(bundle/f)!=h for f,h in value['files'].items())
        or value['counts']!={'optimize':150,'validation':100,'test':300}):
        raise ProtocolViolation('SINGLE_PROMPT_BUNDLE_HASH_OR_SCHEMA_MISMATCH')
    SystemPrompt.from_dict(read(bundle/'initial.json'))
    return value


def load_rows(bundle: Path,role: str,phase: str) -> list[dict]:
    if (phase=='search' and role not in ('optimize','validation') or phase=='test' and role!='test'
        or phase not in ('search','test')):raise ProtocolViolation('SINGLE_PROMPT_SPLIT_ACCESS_FORBIDDEN')
    value=read(bundle/'manifest.json');rows=read(bundle/f'{role}.json')
    if (len(rows)!=value['counts'][role] or digest([r['stable_example_id'] for r in rows])!=value['membership_hashes'][role]
        or file_hash(bundle/f'{role}.json')!=value['files'][f'{role}.json']):
        raise ProtocolViolation('SINGLE_PROMPT_SPLIT_MEMBERSHIP_MISMATCH')
    return rows
