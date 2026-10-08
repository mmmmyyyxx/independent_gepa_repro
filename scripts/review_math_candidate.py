"""Persist an outcome-blind owner decision for a private GEPA proposal request."""
from __future__ import annotations
import argparse
from pathlib import Path

from _bootstrap import ROOT
from independent_gepa.math_comparison.candidate_review import record_decision,verify_request
from independent_gepa.math_comparison.contract import read


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request',type=Path,required=True)
    p.add_argument('--decision',choices=('PASS','REJECT'),required=True)
    p.add_argument('--category',action='append',default=[])
    p.add_argument('--reviewer',required=True)
    p.add_argument('--notes-file',type=Path,required=True)
    p.add_argument('--bundle',type=Path,required=True)
    a=p.parse_args();request=a.request.resolve()
    if not request.is_relative_to((ROOT/'runs').resolve()):
        raise ValueError('PRIVATE_RUN_REVIEW_REQUEST_REQUIRED')
    notes=a.notes_file.resolve()
    if not notes.is_relative_to((ROOT/'runs').resolve()):raise ValueError('PRIVATE_REVIEW_NOTES_REQUIRED')
    verify_request(read(request),read(a.bundle/'optimize.json'),read(a.bundle/'shell.json'))
    record_decision(request,a.decision,a.category,reviewer=a.reviewer,notes=read(notes))
    print('OWNER_DECISION_RECORDED; no provider calls')


if __name__=='__main__':main()
