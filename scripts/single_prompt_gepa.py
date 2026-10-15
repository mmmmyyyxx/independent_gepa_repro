"""Prepare and execute the separately governed native single-Prompt GEPA comparison."""
import argparse
from pathlib import Path
from _bootstrap import ROOT
from independent_gepa.single_prompt_math.common import write,require_private,progress
from independent_gepa.single_prompt_math.bundle import export_bundle
from independent_gepa.single_prompt_math.runner import preflight,freeze,execute,publish


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='mode',required=True)
    e=sub.add_parser('export');e.add_argument('--source',type=Path,required=True);e.add_argument('--output',type=Path,required=True)
    for mode in ('preflight','freeze','run'):
        q=sub.add_parser(mode);q.add_argument('--bundle',type=Path,required=True)
        if mode=='preflight':q.add_argument('--output',type=Path,required=True)
        else:
            q.add_argument('--freeze',type=Path,required=True);q.add_argument('--private-output',type=Path,required=True)
            if mode=='freeze':
                q.add_argument('--authorization',type=Path,required=True);q.add_argument('--gates',type=Path,required=True)
            else:q.add_argument('--execute',action='store_true',required=True)
    q=sub.add_parser('report');q.add_argument('--run',type=Path,required=True);q.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.mode=='export':result=export_bundle(a.source.resolve(),require_private(ROOT,a.output,'data/private_bundles'))
    elif a.mode=='preflight':result=preflight(ROOT,a.bundle.resolve());write(a.output,result)
    elif a.mode=='freeze':result=freeze(ROOT,a.bundle.resolve(),a.authorization.resolve(),a.gates.resolve(),a.freeze.resolve(),a.private_output.resolve())
    elif a.mode=='run':result=execute(ROOT,a.bundle.resolve(),a.freeze.resolve(),a.private_output.resolve())
    else:result=publish(ROOT,a.run.resolve(),a.output.resolve())
    progress('PASS '+a.mode+' '+str(result.get('identity',result.get('status',result.get('bundle_hash','')))))


if __name__=='__main__':main()
