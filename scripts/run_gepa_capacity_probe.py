from __future__ import annotations
import argparse, json
from pathlib import Path
from _bootstrap import ROOT
from independent_gepa.capacity_probe import CapacitySettings, SEEDS, run_capacity_seed, validate_capacity_bundle
from independent_gepa.bundle import write_canonical_json
from independent_gepa.provider import ExactRequestCache, OpenAICompatibleProvider, ProviderAccounting
from independent_gepa.testing import DeterministicFakeTransport

def main() -> None:
 p=argparse.ArgumentParser(description="Run isolated official-GEPA single-prompt capacity folds")
 p.add_argument("--bundle",type=Path,required=True); p.add_argument("--private-output",type=Path,required=True); p.add_argument("--public-output",type=Path,required=True)
 p.add_argument("--seed",type=int,choices=SEEDS); p.add_argument("--offline-fake",action="store_true"); p.add_argument("--allow-real-api",action="store_true")
 p.add_argument("--api-key-env",default="DASHSCOPE_API_KEY"); p.add_argument("--base-url-env",default="DASHSCOPE_BASE_URL"); a=p.parse_args()
 if a.offline_fake == a.allow_real_api: raise RuntimeError("select exactly one transport")
 b=validate_capacity_bundle(a.bundle); reports=[]
 for seed in ((a.seed,) if a.seed else SEEDS):
  private=a.private_output/f"seed_{seed}"; identity=f"capacity-{b.manifest['bundle_hash']}-{seed}"
  common=dict(task_model="qwen3-8b",reflection_model="qwen3.7-flash",temperature=0.0,max_tokens=1800,timeout_seconds=120,max_retries=3,enable_thinking=False,cache=ExactRequestCache(private/"exact_request_cache.json"),accounting=ProviderAccounting(state_path=private/"provider_accounting.json",identity=identity),pricing_per_million_tokens=bundle_pricing(b))
  provider=OpenAICompatibleProvider(transport=DeterministicFakeTransport(),**common) if a.offline_fake else OpenAICompatibleProvider.from_environment(api_key_env=a.api_key_env,base_url_env=a.base_url_env,config_allows_real_api=True,cli_allows_real_api=True,**common)
  reports.append(run_capacity_seed(bundle=b,seed=seed,settings=CapacitySettings(),private_root=a.private_output,public_root=a.public_output,provider=provider))
 write_canonical_json(a.public_output/"summary.json",{"stage":"capacity_probe","reports":reports,"test_access":"denied"}); print("PASS capacity probe")
def bundle_pricing(bundle): return json.loads((bundle.root/"model_contract.json").read_text(encoding="utf-8"))["pricing_per_million_tokens"]
if __name__ == "__main__": main()
