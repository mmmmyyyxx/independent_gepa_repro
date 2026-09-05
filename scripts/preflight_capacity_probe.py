from __future__ import annotations
import argparse
from pathlib import Path
from _bootstrap import ROOT
from verify_environment import verify
from independent_gepa.bundle import sha256_file, write_canonical_json
from independent_gepa.capacity_probe import CapacitySettings, _RecordedStops, validate_capacity_bundle
from independent_gepa.protocol import ProtocolViolation

def main() -> None:
 p=argparse.ArgumentParser(description="Offline gates for the isolated capacity probe")
 p.add_argument("--bundle",type=Path,required=True); p.add_argument("--config",type=Path,default=ROOT/"configs"/"gepa_capacity_probe_disambiguation_qa.yaml"); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
 env=verify(); b=validate_capacity_bundle(a.bundle); text=a.config.read_text(encoding="utf-8")
 required=("stage: capacity_probe","task_model: qwen3-8b","reflection_model: qwen3.7-flash","enable_thinking: false","candidate_selection_strategy: pareto","frontier_type: instance","reflection_minibatch_size: 3","skip_perfect_score: false","use_merge: true","max_merge_invocations: 5","merge_val_overlap_floor: 5","cache_evaluation: false","module_selector: round_robin","no_improvement_patience: 10","max_candidate_proposals: 50")
 if any(value not in text for value in required): raise ProtocolViolation("capacity config does not freeze the required contract")
 CapacitySettings().validate()
 class State:
  def __init__(self,i,score): self.i=i; self.program_full_scores_val_set=[score]
 stops=_RecordedStops(10,50); stops(State(-1,0.5))
 if any(stops(State(i,0.5)) for i in range(9)) or not stops(State(9,0.5)) or stops.reason != "no_improvement_patience_10": raise ProtocolViolation("official no-improvement stopper gate failed")
 cap=_RecordedStops(10,50)
 if not cap(State(49,0.5)) or cap.reason != "max_candidate_proposals_50": raise ProtocolViolation("candidate proposal stopper gate failed")
 try: _=b.test_examples
 except ProtocolViolation: pass
 else: raise ProtocolViolation("Test50 access-denial gate failed")
 source=(ROOT/"src"/"independent_gepa"/"capacity_probe.py").read_text(encoding="utf-8")
 if "RemainingLogicalBudgetStopper" in source or "token_budget_policy" in source: raise ProtocolViolation("matched budget stopper leaked into capacity stage")
 report={"stage":"capacity_probe","gate":"PASS","bundle_hash":b.manifest["bundle_hash"],"config_sha256":sha256_file(a.config),"gepa_commit":env["gepa_commit"],"split_identity":"PASS","p0_identity":"PASS","parser_parity":"PASS","test_access_denial":"PASS","official_stoppers":"PASS","model_route_contract":"PASS","matched_budget_stopper_inactive":"PASS"}
 write_canonical_json(a.output,report); print("PASS capacity preflight")
if __name__ == "__main__": main()
