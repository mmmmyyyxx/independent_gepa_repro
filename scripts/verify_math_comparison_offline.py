"""Record complete zero-provider gates under an explicit network/credential guard."""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import xml.etree.ElementTree as ET

from _bootstrap import ROOT
from independent_gepa.math_comparison.contract import digest,file_hash,write,source_inventory
from independent_gepa.math_comparison.runner import preflight
from independent_gepa.math_comparison.benchmark import matrix
from independent_gepa.audit import audit_public_paths

def main():
    p=argparse.ArgumentParser(description='Offline MATH comparison gates')
    p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--config',type=Path,default=ROOT/'configs/math_a4_matched.yaml')
    p.add_argument('--source',type=Path,required=True);a=p.parse_args()
    # Never make inherited secrets available to pytest or evaluator subprocesses.
    for name in list(os.environ):
        if 'API_KEY' in name or 'BASE_URL' in name: os.environ.pop(name,None)
    os.environ['PYTHONPATH']=str(ROOT/'src')
    def blocked(*args,**kwargs): raise RuntimeError('OFFLINE_NETWORK_FORBIDDEN')
    socket.socket.connect=socket.socket.connect_ex=socket.create_connection=socket.getaddrinfo=blocked
    private=ROOT/'reports/private/math_a4_offline_gates';private.mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,'-m','compileall','-q','src','scripts','tests'],cwd=ROOT,check=True)
    junit=private/'pytest.xml'
    # Block outgoing calls for the entire suite, including older tests.
    command="import socket,pytest;"+\
        "socket.socket.connect=socket.socket.connect_ex=socket.create_connection=socket.getaddrinfo=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('OFFLINE_NETWORK_FORBIDDEN'));"+\
        f"raise SystemExit(pytest.main(['-q','--disable-warnings','--junitxml={junit.as_posix()}']))"
    subprocess.run([sys.executable,'-c',command],cwd=ROOT,check=True)
    suites=ET.parse(junit).getroot().findall('testsuite')
    passed=sum(int(s.get('tests','0'))-int(s.get('failures','0'))-int(s.get('errors','0'))-int(s.get('skipped','0')) for s in suites)
    result=preflight(ROOT,a.bundle.resolve(),a.config.resolve())
    # Parser/scorer copying audit: no algorithm code differs from A4.
    worker=a.source/'multi_dataset_diverse_rl/benchmarks/math_domain_worker.py'
    expected=worker.read_text(encoding='utf-8').replace('from .math_worker import PINS','from .contract import PINS').replace('from .math_domain_v2 import SETTINGS','from .contract import SETTINGS')
    local=ROOT/'src/independent_gepa/math_comparison/math_domain_worker.py'
    if expected!=local.read_text(encoding='utf-8'): raise RuntimeError('MATH_WORKER_PARITY_FAILED')
    pred=a.source/'multi_dataset_diverse_rl/benchmarks/math_prediction_worker.py'
    if pred.read_bytes()!=(local.parent/'math_prediction_worker.py').read_bytes(): raise RuntimeError('PREDICTION_WORKER_PARITY_FAILED')
    # Independent process comparison on synthetic expressions only; no sibling import in this runtime.
    fixtures=('1','0.5','\\frac{1}{2}','x=1','(1,2)','\\{1,2\\}')
    inherited={**os.environ,'PYTHONPATH':str(a.source.resolve())}
    source_result=subprocess.run([sys.executable,'-m','multi_dataset_diverse_rl.benchmarks.math_domain_worker'],
        input=json.dumps({'expressions':fixtures}),capture_output=True,text=True,cwd=a.source,
        env=inherited,timeout=8,check=True)
    if json.loads(source_result.stdout)!=matrix(fixtures): raise RuntimeError('SCORER_GOLDEN_PARITY_FAILED')
    # Explicit structural preflight: unanimous four fixed valid peers pin Vote.
    from independent_gepa.math_comparison.contract import read
    original=read(a.bundle/'audit_only/initial.json');profiles=original['profiles'];locked=0
    for index in range(60):
        row=[m[index] for m in profiles]
        if all(r['prediction_valid'] for r in row):
            relation=matrix(tuple(r['answer'] for r in row))['equivalence']
            locked+=all(all(r) for r in relation)
    zero_valid=sum(not any(m[i]['prediction_valid'] for m in profiles) for i in range(60))
    unanimous_correctness=all(len(set(row))==1 for row in original['correctness'])
    public_snapshot={**result,'pytest_passed':passed,'compileall':'PASS','fake_seven_window_e2e':'PASS',
        'copied_worker_code_parity':'PASS','synthetic_scorer_process_parity':'PASS',
        'historical_unanimous_vote_locked_examples':locked,
        'Vote_metric_structurally_invariant':locked==60,
        'historical_all_invalid_examples':zero_valid,
        'historical_correctness_unanimous':unanimous_correctness,
        'single_member_vote_gain_upper_bound':zero_valid if unanimous_correctness else None,
        'historical_private_replay_suite':'NOT_RUN; sibling repository remains read-only',
        'source_inventory_hash':digest(source_inventory(ROOT))}
    if audit_public_paths([ROOT/'docs/math_a4_comparison_v1.md']): raise RuntimeError('PROTOCOL_SANITIZATION_FAILED')
    if audit_public_paths([ROOT/'docs/math_a4_copy_guard_repair_v1.md']): raise RuntimeError('REPAIR_PROTOCOL_SANITIZATION_FAILED')
    if audit_public_paths([ROOT/'docs/math_a4_guarded_comparison_v3.md']): raise RuntimeError('CURRENT_PROTOCOL_SANITIZATION_FAILED')
    subprocess.run(['git','diff','--check'],cwd=ROOT,check=True)
    write(a.output.resolve(),public_snapshot)
    print(f'PASS offline gates: {passed} tests, zero provider calls, Vote-locked examples={locked}')

if __name__=='__main__': main()
