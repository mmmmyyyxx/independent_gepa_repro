"""Pinned parsing and verifier, preceded by bounded exact separation certificates."""
import json
import socket
import sys

from ..math_comparison import math_domain_worker as pinned
from .certified_bounds import definitely_separated
from .common import digest
from .scoring_v5 import validate_policy


def evaluate(reference,prediction,policy):
    validate_policy(policy)
    gold,gold_valid=pinned.parse_payload(reference)
    if not gold_valid or not pinned.verify_payload(gold,gold):raise ValueError('REFERENCE_UNSCORABLE')
    if prediction is None:return {'reference_valid':True,'correct':False,'policy_sha256':digest(policy),'certificate':False}
    parsed,valid=pinned.parse_payload(prediction)
    certificate=False;correct=False
    if valid:
        for g in gold:
            for p in parsed:
                if not pinned.compatible(g,p):continue
                if definitely_separated(g,p,policy):certificate=True;continue
                if pinned.verify_payload([g],[p]):correct=True;break
            if correct:break
    return {'reference_valid':True,'correct':correct,'policy_sha256':digest(policy),'certificate':certificate}


def main():
    def blocked(*args,**kwargs):raise RuntimeError('SCORING_WORKER_NETWORK_FORBIDDEN')
    socket.socket.connect=socket.socket.connect_ex=socket.create_connection=socket.getaddrinfo=blocked
    try:
        pinned.initialize();data=json.load(sys.stdin)
        json.dump(evaluate(data['reference'],data['prediction'],data['policy']),sys.stdout);return 0
    except Exception:
        json.dump({'error':'SCORING_V5_FAILURE'},sys.stdout);return 1


if __name__=='__main__':raise SystemExit(main())
