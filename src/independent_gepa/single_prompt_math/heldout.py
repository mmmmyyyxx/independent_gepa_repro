"""Data-only eligibility checks: absence from one split is not exposure proof."""
from pathlib import Path
import re

from .common import digest, file_hash, read, write
from ..protocol import ProtocolViolation

REQUIRED_SCOPES = {'optimizer_inputs', 'human_error_analysis', 'scorer_repair', 'method_tuning'}


def input_identity(row):
    return digest(re.sub(r'\s+',' ',row['content']['problem']).strip())


def validate_exposure(exposure,root=None):
    if (exposure.get('identity') != 'REVIEWED_COMPLETE_EXPOSURE_INVENTORY_V1'
        or exposure.get('owner_reviewed_complete') is not True
        or set(exposure.get('scopes', [])) != REQUIRED_SCOPES or not exposure.get('files')):
        raise ProtocolViolation('COMPLETE_EXPOSURE_PROOF_REQUIRED')
    if root is not None:
        for relative,sha in exposure['files'].items():
            path=(root/relative).resolve()
            if not path.is_relative_to(root.parent.resolve()) or file_hash(path)!=sha:
                raise ProtocolViolation('EXPOSURE_EVIDENCE_HASH_MISMATCH')


def assess(root, bundle):
    registries = [p for base in (root / 'data', root.parent / 'multi_agent_diversity/data')
                  for p in base.rglob('*exposure*') if p.is_file()]
    canonical = root.parent / 'multi_agent_diversity/data/benchmark_suite_v1/raw/math'
    sources = [p for p in canonical.glob('*.jsonl') if p.is_file()]
    return {'identity': 'GEPA_HELDOUT_ELIGIBILITY_ASSESSMENT_V6',
        'status': 'UNVERIFIED_NO_COMPLETE_EXPOSURE_PROOF',
        'raw_source_file_count': len(sources), 'exposure_named_artifact_count': len(registries),
        'fresh_confirmatory_available': False, 'fresh_set_frozen': False,
        'reason': 'No reviewed complete cross-experiment and human-analysis exposure inventory is bound. Unused canonical rows alone cannot prove freshness.',
        'historical_test_membership_hash': read(bundle / 'manifest.json')['membership_hashes']['test'],
        'historical_test_renamed_or_resplit': False,
        'primary_test_if_separately_authorized': 'historical_exploratory_only'}


def freeze_fresh(root, bundle, candidates, exposure, output, count=300):
    if output.exists() or count != 300:
        raise ProtocolViolation('FRESH_HELDOUT_PATH_AND_COUNT_REQUIRED')
    validate_exposure(exposure,root)
    excluded_ids = set(exposure.get('stable_ids', []))
    excluded_inputs = set(exposure.get('input_hashes', []))
    excluded_content=set()
    for split in ('optimize', 'validation', 'test'):
        for row in read(bundle / (split + '.json')):
            excluded_ids.add(row['stable_example_id'])
            excluded_inputs.add(row.get('input_sha256', digest(row['content']['problem'])))
            excluded_content.add(input_identity(row))
    eligible = [r for r in candidates if r['stable_example_id'] not in excluded_ids
                and r.get('input_sha256', digest(r['content']['problem'])) not in excluded_inputs
                and input_identity(r) not in excluded_content]
    if len({r['stable_example_id'] for r in eligible}) != len(eligible) or len(eligible) < count:
        raise ProtocolViolation('INSUFFICIENT_UNEXPOSED_HELDOUT_MEMBERS')
    chosen = sorted(eligible, key=lambda r: digest({'seed': 42, 'id': r['stable_example_id']}))[:count]
    write(output / 'test.json', chosen)
    write(output / 'exposure_inventory.json',exposure)
    manifest = {'identity': 'GEPA_FRESH_HELDOUT_V6', 'count': count, 'membership_hash': digest([r['stable_example_id'] for r in chosen]),
        'content_hash': digest(chosen), 'test_file_sha256': file_hash(output / 'test.json'),
        'exposure_inventory_sha256': digest(exposure), 'reviewed_exposure_scope': sorted(REQUIRED_SCOPES),
        'parent_bundle_hash':read(bundle/'manifest.json')['bundle_hash']}
    write(output / 'manifest.json', manifest)
    return manifest


def contract(bundle, fresh=None, *,root=None):
    if fresh is None:
        manifest = read(bundle / 'manifest.json')
        return {'mode': 'historical_exploratory', 'count': 300,
                'membership_hash': manifest['membership_hashes']['test'],
                'test_file_sha256': manifest['files']['test.json'], 'fresh_path': None}
    manifest = read(fresh / 'manifest.json')
    rows = read(fresh / 'test.json')
    exposure=read(fresh/'exposure_inventory.json')
    validate_exposure(exposure,root)
    if (manifest.get('identity') != 'GEPA_FRESH_HELDOUT_V6' or len(rows) != 300
        or file_hash(fresh / 'test.json') != manifest['test_file_sha256']
        or digest(rows) != manifest['content_hash'] or digest([r['stable_example_id'] for r in rows]) != manifest['membership_hash']
        or digest(exposure)!=manifest['exposure_inventory_sha256']
        or manifest['parent_bundle_hash']!=read(bundle/'manifest.json')['bundle_hash']):
        raise ProtocolViolation('FRESH_TEST_CONTRACT_MISMATCH')
    original=[r for split in ('optimize','validation','test') for r in read(bundle/(split+'.json'))]
    if (len({r['stable_example_id'] for r in rows})!=300
        or {r['stable_example_id'] for r in rows}&({r['stable_example_id'] for r in original}|set(exposure.get('stable_ids',[])))
        or {input_identity(r) for r in rows}&{input_identity(r) for r in original}
        or {r.get('input_sha256',input_identity(r)) for r in rows}&set(exposure.get('input_hashes',[]))):
        raise ProtocolViolation('FRESH_TEST_EXPOSURE_OR_RENAMED_MEMBERS')
    return {'mode': 'reviewed_fresh_heldout', 'count': 300, 'membership_hash': manifest['membership_hash'],
            'test_file_sha256': manifest['test_file_sha256'], 'fresh_path': fresh.as_posix(),
            'manifest_sha256': file_hash(fresh / 'manifest.json')}


def load_test(bundle, specification, root=None):
    if specification['mode'] == 'historical_exploratory':
        path = bundle / 'test.json'
    elif specification['mode'] == 'reviewed_fresh_heldout':
        path = Path(specification['fresh_path'])
        if not path.is_absolute():
            if root is None:
                raise ProtocolViolation('HELDOUT_ROOT_REQUIRED')
            path = root / path
        if file_hash(path / 'manifest.json') != specification['manifest_sha256']:
            raise ProtocolViolation('FROZEN_HELDOUT_CHANGED')
        path = path / 'test.json'
        if root is not None:
            validated=contract(bundle,path.parent,root=root)
            if validated['membership_hash']!=specification['membership_hash']:
                raise ProtocolViolation('FROZEN_HELDOUT_EXPOSURE_CHANGED')
    else:
        raise ProtocolViolation('UNKNOWN_TEST_EXPOSURE_POLICY')
    rows = read(path)
    if (file_hash(path) != specification['test_file_sha256'] or len(rows) != specification['count']
        or digest([r['stable_example_id'] for r in rows]) != specification['membership_hash']):
        raise ProtocolViolation('TEST_MEMBERSHIP_OR_HASH_CHANGED')
    return rows
