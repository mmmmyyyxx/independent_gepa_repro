"""Independently audit a complete frozen V4 run with no provider requests."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import socket
from _bootstrap import ROOT
from independent_gepa.math_comparison.integrity import audit_complete
from independent_gepa.math_comparison.contract import write
from independent_gepa.audit import audit_public_paths


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    for key in list(os.environ):
        if 'API_KEY' in key or 'BASE_URL' in key:os.environ.pop(key,None)
    def blocked(*args,**kwargs):raise RuntimeError('OFFLINE_NETWORK_FORBIDDEN')
    socket.socket.connect=socket.socket.connect_ex=socket.create_connection=socket.getaddrinfo=blocked
    value=audit_complete(ROOT,a.run.resolve(),a.bundle.resolve());write(a.output,value)
    if audit_public_paths([a.output]):raise RuntimeError('PUBLIC_AUDIT_SANITIZATION_FAILURE')
    print('PASS complete receipt/scoring/split/budget audit; '+value['scientific_status'])


if __name__=='__main__':main()
