from __future__ import annotations

import argparse
from pathlib import Path
from _bootstrap import ROOT
from independent_gepa.math_comparison.contract import export_bundle,write
from independent_gepa.math_comparison.runner import execute,freeze,preflight

def main() -> None:
    parser=argparse.ArgumentParser(description='Frozen independent native GEPA versus A4 MATH comparison')
    sub=parser.add_subparsers(dest='mode',required=True)
    export=sub.add_parser('export');export.add_argument('--source',type=Path,required=True);export.add_argument('--output',type=Path,required=True)
    for mode in ('preflight','freeze','run'):
        p=sub.add_parser(mode);p.add_argument('--bundle',type=Path,required=True)
        p.add_argument('--config',type=Path,default=ROOT/'configs/math_a4_matched.yaml')
        if mode=='preflight': p.add_argument('--output',type=Path,required=True)
        else:
            p.add_argument('--freeze',type=Path,required=True);p.add_argument('--private-output',type=Path,required=True)
            p.add_argument('--public-output',type=Path,required=True)
            if mode=='freeze':
                p.add_argument('--task-file',type=Path,required=True);p.add_argument('--gates',type=Path,required=True)
            else: p.add_argument('--allow-real-api',action='store_true')
    args=parser.parse_args()
    if args.mode=='export':
        identity=export_bundle(args.source.resolve(),args.output.resolve());print('PASS bundle '+identity);return
    bundle=args.bundle.resolve();config=args.config.resolve()
    if args.mode=='preflight':
        value=preflight(ROOT,bundle,config);write(args.output,value);print('PASS offline preflight');return
    common=(ROOT,bundle,config)
    if args.mode=='freeze':
        value=freeze(*common,args.task_file.resolve(),args.gates.resolve(),args.freeze.resolve(),
                     args.private_output.resolve(),args.public_output.resolve())
        print('PASS frozen single-use attempt '+value['identity'])
    else:
        value=execute(*common,args.freeze.resolve(),args.private_output.resolve(),args.public_output.resolve(),
                      allow_real_api=args.allow_real_api)
        print(value['status'])

if __name__=='__main__': main()
