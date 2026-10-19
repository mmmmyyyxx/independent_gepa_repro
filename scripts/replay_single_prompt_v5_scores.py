"""Offline mathematical parity only. Never opens a provider or edits parent evidence."""
import argparse
import os
from pathlib import Path
import socket

from _bootstrap import ROOT


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('bundle','parent','output'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    for name in list(os.environ):
        if 'API_KEY' in name or 'BASE_URL' in name:os.environ.pop(name,None)
    def blocked(*args,**kwargs):raise RuntimeError('OFFLINE_NETWORK_FORBIDDEN')
    socket.socket.connect=socket.socket.connect_ex=socket.create_connection=socket.getaddrinfo=blocked
    from independent_gepa.single_prompt_math.runner import load_config
    from independent_gepa.single_prompt_math.replay_scores import replay
    result=replay(ROOT,a.bundle.resolve(),a.parent.resolve(),load_config(ROOT),a.output.resolve())
    print('PASS old-score replay: '+str(result['unchanged'])+' unchanged; model calls=0')


if __name__=='__main__':main()
