"""Read-only replay of the exact 5,346 historically graded observations."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from types import SimpleNamespace

from .common import digest, file_hash, read, write, progress
from .recovery import retry_local_worker
from .scoring import score, IDENTITY, algorithm_policy
from ..protocol import ProtocolViolation


def replay(root, bundle, parent, config, output):
    files = sorted((parent / 'cache').glob('*.json'))
    if len(files) != 5346:
        raise ProtocolViolation('EXACT_5346_HISTORICAL_GRADES_REQUIRED')
    inventory = {p.name:file_hash(p) for p in files}
    rows = {r['stable_example_id']:r for split in ('optimize','validation','test') for r in read(bundle/(split+'.json'))}
    def grade(path):
        value = read(path)
        reference = rows[value['example_id']]['reference_final_answer']
        prediction = SimpleNamespace(prediction_valid=value['valid'],answer=value['answer'])
        answer = retry_local_worker(lambda:score(prediction,reference),config,
            config['local_worker_initial_deadlines_seconds'][value['phase']])
        return answer == value['correct']
    equal = 0
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(grade,p) for p in files]
        for number, future in enumerate(as_completed(futures),1):
            equal += future.result()
            if number % 500 == 0:
                progress(f'OLD_SCORE_REPLAY completed={number}/5346 equal={equal}')
    if inventory != {p.name:file_hash(p) for p in files}:
        raise ProtocolViolation('HISTORICAL_GRADES_CHANGED_DURING_REPLAY')
    algorithm_files = ('scoring.py','scoring_v5.py','scoring_worker_v5.py','certified_bounds.py')
    result = {'identity':'V6_ALL_PHASE_SCORER_5346_PARITY','status':'PASS' if equal==5346 else 'FAIL',
        'observations':5346,'unchanged':equal,'changed':5346-equal,'scoring_binding':IDENTITY,
        'algorithm_policy_sha256':digest(algorithm_policy()),'parent_cache_inventory_sha256':digest(inventory),
        'algorithm_file_hashes':{name:file_hash(root/'src/independent_gepa/single_prompt_math'/name) for name in algorithm_files},
        'parent_unchanged':True,'new_model_calls':0,'new_model_tokens':0}
    write(output,result)
    if equal != 5346:
        raise ProtocolViolation('HISTORICAL_MATHEMATICAL_SCORE_PARITY_FAILED')
    return result
