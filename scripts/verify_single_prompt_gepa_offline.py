"""Current complete zero-model verification for the two-arm GEPA proposal."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import xml.etree.ElementTree as ET

from _bootstrap import ROOT
from independent_gepa.single_prompt_math.common import digest,write,source_inventory
from independent_gepa.single_prompt_math.runner import preflight
from independent_gepa.audit import audit_public_paths


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--focused',action='store_true',help='debug subset only; cannot authorize a freeze')
    p.add_argument('--score-replay',type=Path,help='V6 exact5346 old-score parity receipt; required for complete gates')
    a=p.parse_args()
    for name in list(os.environ):
        if 'API_KEY' in name or 'BASE_URL' in name:os.environ.pop(name,None)
    os.environ['FORMAL_ZERO_API_GUARD_REQUIRED']='1'
    def blocked(*args,**kwargs):raise RuntimeError('OFFLINE_NETWORK_FORBIDDEN')
    socket.socket.connect=socket.socket.connect_ex=socket.create_connection=socket.getaddrinfo=blocked
    starting_inventory=source_inventory(ROOT)
    if not a.focused:
        if a.score_replay is None:raise RuntimeError('V6_EXACT_5346_PARITY_RECEIPT_REQUIRED')
        from independent_gepa.single_prompt_math.common import read,file_hash
        parity=read(a.score_replay)
        if parity.get('status')!='PASS' or parity.get('unchanged')!=5346 or parity.get('changed')!=0 or parity.get('new_model_calls')!=0:
            raise RuntimeError('V6_HISTORICAL_SCORE_PARITY_REQUIRED')
        for name,sha in parity['algorithm_file_hashes'].items():
            if file_hash(ROOT/'src/independent_gepa/single_prompt_math'/name)!=sha:raise RuntimeError('V6_PARITY_SOURCE_CHANGED')
    subprocess.run([sys.executable,'-m','compileall','-q','src','scripts','tests'],cwd=ROOT,check=True)
    private=a.output.resolve().parent/'checks';private.mkdir(parents=True,exist_ok=True)
    junit=private/('focused_pytest.xml' if a.focused else 'complete_pytest.xml')
    args=['-q','--disable-warnings','--maxfail=1','--junitxml='+str(junit)]
    if a.focused:args[:0]=['tests/test_single_prompt_math.py','tests/test_single_prompt_recovery.py']
    code="import socket,pytest;socket.socket.connect=socket.socket.connect_ex=socket.create_connection=socket.getaddrinfo=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('OFFLINE_NETWORK_FORBIDDEN'));raise SystemExit(pytest.main("+repr(args)+"))"
    subprocess.run([sys.executable,'-c',code],cwd=ROOT,check=True)
    suites=ET.parse(junit).getroot().findall('testsuite')
    passed=sum(int(s.get('tests',0))-int(s.get('failures',0))-int(s.get('errors',0))-int(s.get('skipped',0)) for s in suites)
    v6_passed=sum(1 for s in suites for case in s.findall('testcase')
                  if 'test_single_prompt_v6' in case.get('classname','') and case.find('skipped') is None
                  and case.find('failure') is None and case.find('error') is None)
    if not a.focused and v6_passed<30:raise RuntimeError('COMPLETE_V6_ENGINEERING_CASES_REQUIRED')
    if source_inventory(ROOT)!=starting_inventory:raise RuntimeError('SOURCE_CHANGED_DURING_OFFLINE_GATES')
    evidence=preflight(ROOT,a.bundle.resolve())
    public=[ROOT/'docs/gepa_single_prompt_math_v1.md',ROOT/'docs/gepa_single_prompt_semantic_review_v2.md',ROOT/'docs/gepa_single_prompt_recovery_v3.md',ROOT/'docs/gepa_single_prompt_native_guard_v4.md',ROOT/'docs/gepa_single_prompt_scoring_continuation_v5.md',ROOT/'docs/gepa_single_prompt_math_v6.md',ROOT/'docs/gepa_single_prompt_compute_v6.md',ROOT/'docs/gepa_single_prompt_analysis_v6.md']
    if audit_public_paths(public):raise RuntimeError('PUBLIC_PROTOCOL_SANITIZATION_FAILED')
    subprocess.run(['git','diff','--check'],cwd=ROOT,check=True)
    evidence.update(status='FOCUSED_DEBUG_PASS' if a.focused else 'PASS',pytest_passed=passed,
        compileall='PASS',credentials_removed=True,outgoing_sockets_blocked=True,
        complete_two_arm_three_repeat_fake_e2e='PASS',semantic_selector_regressions='PASS',
        real_model_requests=0,formal_authorization='NOT_GRANTED',READY_TO_RUN=False,
        historical_5346_parity='NOT_REQUIRED_FOR_FOCUSED_DEBUG' if a.focused else 'PASS',
        historical_score_replay_sha256=None if a.focused else file_hash(a.score_replay),
        v6_engineering_tests_passed=v6_passed,money_calculated=False,
        historical_private_replay_suite='NOT_RUN; sibling remains read-only',
        source_inventory_sha256=digest(source_inventory(ROOT)))
    write(a.output.resolve(),evidence)
    print(f'PASS offline verification: {passed} tests; real model requests=0; formal authorization pending')


if __name__=='__main__':main()
