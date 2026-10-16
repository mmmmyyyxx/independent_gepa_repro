"""Prepare, freeze and execute one explicitly authorized sealed-Test continuation."""
import argparse
from pathlib import Path
from _bootstrap import ROOT
from independent_gepa.single_prompt_math import continuation
from independent_gepa.single_prompt_math.common import progress


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='mode',required=True)
    q=sub.add_parser('prepare');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--parent',type=Path,required=True)
    q.add_argument('--output',type=Path,required=True);q.add_argument('--receipt',type=Path,required=True)
    q=sub.add_parser('freeze')
    for name in ('bundle','preparation','authorization','gates','output'):q.add_argument('--'+name,type=Path,required=True)
    q=sub.add_parser('run');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--freeze',type=Path,required=True)
    q.add_argument('--execute',action='store_true',required=True)
    q=sub.add_parser('report');q.add_argument('--run',type=Path,required=True);q.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.mode=='prepare':result=continuation.prepare(ROOT,a.bundle.resolve(),a.parent.resolve(),a.output.resolve(),a.receipt.resolve())
    elif a.mode=='freeze':result=continuation.freeze(ROOT,a.bundle.resolve(),a.preparation.resolve(),a.authorization.resolve(),a.gates.resolve(),a.output.resolve())
    elif a.mode=='run':result=continuation.execute(ROOT,a.bundle.resolve(),a.freeze.resolve())
    else:result=continuation.publish(ROOT,a.run.resolve(),a.output.resolve())
    progress('PASS '+a.mode+' '+str(result.get('status',result.get('identity',''))))


if __name__=='__main__':main()
