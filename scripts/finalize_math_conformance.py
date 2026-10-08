"""Prepare an outcome-blind pool and record the actual owner's final review."""
from __future__ import annotations
import argparse
from pathlib import Path
from _bootstrap import ROOT
from independent_gepa.math_comparison.pool_review import prepare_pool,finalize_pool
from independent_gepa.math_comparison.contract import read,write


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','finalize'))
    p.add_argument('--run',type=Path,required=True);p.add_argument('--bundle',type=Path,required=True)
    p.add_argument('--reviewer');p.add_argument('--notes-file',type=Path)
    a=p.parse_args();run=a.run.resolve()
    if not run.is_relative_to((ROOT/'runs').resolve()):raise ValueError('PRIVATE_RUN_REQUIRED')
    if a.mode=='prepare':write(run/'outcome_blind_pool_manifest.json',prepare_pool(run,a.bundle.resolve()))
    else:
        if a.reviewer is None or a.notes_file is None:raise ValueError('ACTUAL_FINAL_OWNER_REVIEW_REQUIRED')
        notes=a.notes_file.resolve()
        if not notes.is_relative_to(run):raise ValueError('PRIVATE_OWNER_NOTES_REQUIRED')
        finalize_pool(run,a.bundle.resolve(),a.reviewer,read(notes))
    print('PASS outcome-blind conformance '+a.mode+'; provider calls=0')


if __name__=='__main__':main()
