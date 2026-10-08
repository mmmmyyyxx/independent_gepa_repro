"""Offline replay of a new copy guard over immutable historical proposals."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import socket

from _bootstrap import ROOT
from independent_gepa.audit import audit_public_paths
from independent_gepa.math_comparison.candidate_guard import GUARD_ID, candidate_failures
from independent_gepa.math_comparison.contract import digest, file_hash, read, write


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--private-run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    for name in list(os.environ):
        if 'API_KEY' in name or 'BASE_URL' in name: os.environ.pop(name,None)
    def blocked(*args,**kwargs): raise RuntimeError('OFFLINE_NETWORK_FORBIDDEN')
    socket.socket.connect=socket.socket.connect_ex=socket.create_connection=socket.getaddrinfo=blocked
    run=args.private_run.resolve()
    inventory=read(run/'owner_stop/raw_inventory.json')
    # Original owner-stop inventory contains only files existing at termination.
    originals=inventory['files'] if isinstance(inventory,dict) and 'files' in inventory else inventory
    for name, sha in originals.items():
        if file_hash(run/name)!=sha: raise RuntimeError('PRESERVED_RAW_FILE_CHANGED')
    examples=read(args.bundle/'optimize.json')
    closed=read(run/'SEARCH_COMPLETE.json')
    rows=[]
    for selection in closed['selections']:
        selected=set(selection['selected_hashes'])
        for proposal in read(run/f'window_{selection["window"]}/proposals.json'):
            failures=candidate_failures(proposal['prompt'],examples)
            rows.append({'window':selection['window'],'member':selection['member'],
                'generation':proposal['generation'],'prompt_hash':proposal['prompt_hash'],
                'selected_for_audit':proposal['prompt_hash'] in selected,
                'original_guard_pass':proposal['contract_valid'],
                'repaired_guard_pass':not failures,'failure_categories':failures})
    value={'status':'OFFLINE_CONFORMANCE_REPLAY_COMPLETE','candidate_guard':GUARD_ID,
        'original_attempt_identity':closed['identity'],'original_selection_hash':closed['selection_hash'],
        'original_source_immutable':True,'original_raw_inventory_hash':digest(originals),
        'proposal_count':len(rows),'selected_count':sum(r['selected_for_audit'] for r in rows),
        'selected_failed_new_guard':sum(r['selected_for_audit'] and not r['repaired_guard_pass'] for r in rows),
        'previous_guard_missed_count':sum(r['original_guard_pass'] and not r['repaired_guard_pass'] for r in rows),
        'semantic_novelty_certified':False,'provider_calls':0,'candidates':rows}
    write(args.output,value)
    if audit_public_paths([args.output]): raise RuntimeError('GUARD_AUDIT_SANITIZATION_FAILED')
    print(f'PASS offline copy-guard replay: proposals={len(rows)} previously_missed={value["previous_guard_missed_count"]}')


if __name__=='__main__': main()
