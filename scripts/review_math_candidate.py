"""Persist an outcome-blind owner decision for a private GEPA proposal request."""
from __future__ import annotations
import argparse
from pathlib import Path

from _bootstrap import ROOT
from independent_gepa.math_comparison.candidate_review import record_decision


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request',type=Path,required=True)
    p.add_argument('--decision',choices=('PASS','REJECT'),required=True)
    p.add_argument('--category',action='append',default=[])
    a=p.parse_args();request=a.request.resolve()
    if not request.is_relative_to((ROOT/'runs').resolve()):
        raise ValueError('PRIVATE_RUN_REVIEW_REQUEST_REQUIRED')
    record_decision(request,a.decision,a.category)
    print('OWNER_DECISION_RECORDED; no provider calls')


if __name__=='__main__':main()
