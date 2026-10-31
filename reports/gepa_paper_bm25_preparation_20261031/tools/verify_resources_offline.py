"""Run either archived resource tool with credentials removed and sockets denied.

Use --python for the frozen paper environment, --guard-workspace for a fresh
ignored evidence parent, then the tool filename and its ordinary arguments.
This wrapper cannot dispatch the experiment runner or a model client.
"""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--guard-workspace', type=Path, required=True)
    parser.add_argument('tool', choices=['disk_bm25_build.py', 'validate_full_index.py'])
    args, rest = parser.parse_known_args()
    root = Path(__file__).resolve().parents[3]
    guard = args.guard_workspace.resolve() / uuid.uuid4().hex
    guard.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(root / 'tests/paper_zero_network/sitecustomize.py', guard / 'sitecustomize.py')
    markers = ['API_KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'CREDENTIAL', 'AUTHORIZATION', 'BASE_URL']
    environment = {key: value for key, value in os.environ.items()
                   if not any(marker in key.upper() for marker in markers)}
    events = guard / 'events.txt'
    environment.update(PYTHONPATH=os.pathsep.join([str(guard), str(root / 'src')]),
                       PAPER_OFFLINE_EVENTS=str(events), PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
                       OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
                       LITELLM_LOCAL_MODEL_COST_MAP='True', HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1',
                       DO_NOT_TRACK='1', WANDB_MODE='offline', DSPY_CACHEDIR=str(guard / 'dspy_cache'))
    result = subprocess.run([str(args.python.resolve()), str(Path(__file__).with_name(args.tool)), *rest],
                            cwd=root, env=environment)
    attempts = len(events.read_text().splitlines()) if events.exists() else 0
    receipt = dict(returncode=result.returncode, all_children_network_attempts=attempts,
                   model_api_calls=0, credentials_scrubbed=True)
    (guard / 'receipt.json').write_text(json.dumps(receipt) + '\n')
    print(json.dumps(receipt))
    raise SystemExit(result.returncode or bool(attempts))


if __name__ == '__main__':
    main()
