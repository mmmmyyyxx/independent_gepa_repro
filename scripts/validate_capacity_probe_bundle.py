from __future__ import annotations
import argparse
from pathlib import Path
from _bootstrap import ROOT
from independent_gepa.capacity_probe import validate_capacity_bundle
def main() -> None:
 p=argparse.ArgumentParser(); p.add_argument("--bundle",type=Path,required=True); a=p.parse_args(); b=validate_capacity_bundle(a.bundle); print(f"PASS capacity bundle={b.manifest['bundle_hash']}")
if __name__ == "__main__": main()
