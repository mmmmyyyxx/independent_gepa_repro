from __future__ import annotations
import argparse
from pathlib import Path
from _bootstrap import ROOT
from independent_gepa.capacity_probe import export_capacity_bundle

def main() -> None:
    p=argparse.ArgumentParser(description="Freeze the capacity-probe source artifact without importing sibling code")
    p.add_argument("--source-root", type=Path, default=ROOT.parent / "multi_agent_diversity")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--prompt-carrier", type=Path, default=ROOT.parent / "comparison_bundles" / "v17_split_models_20260903" / "disambiguation_qa_v17_seed56_qwen3_8b_flash_v1" / "initialization" / "agent_0.txt")
    p.add_argument("--d0-manifest", type=Path, default=ROOT.parent / "multi_agent_diversity" / "runs" / "anti_overfitting_shadow_gate_v1_20260904_retry2" / "initialization" / "seed75" / "frozen_initialization_manifest.json")
    a=p.parse_args(); print("PASS bundle="+export_capacity_bundle(source_root=a.source_root,prompt_carrier=a.prompt_carrier,d0_manifest=a.d0_manifest,output=a.output))
if __name__ == "__main__": main()
