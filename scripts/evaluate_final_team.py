from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from _bootstrap import ROOT

from independent_gepa.audit import require_clean_public_artifacts
from independent_gepa.budget import BudgetLedger
from independent_gepa.bundle import prompt_hash, validate_bundle, write_canonical_json
from independent_gepa.evaluator import MemberEvaluator
from independent_gepa.final_evaluator import FinalTeamEvaluator, initial_accuracies_from_bundle
from independent_gepa.parser import StrictAnswerParser
from independent_gepa.protocol import SplitAccessController, SplitName
from independent_gepa.provider import OpenAICompatibleProvider, ProviderAccounting
from independent_gepa.runner import RunConfig
from independent_gepa.testing import DeterministicFakeTransport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate one frozen five-prompt team")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "independent_gepa.yaml")
    parser.add_argument("--team", type=Path, required=True, help="private frozen-team JSON")
    parser.add_argument("--split", choices=["development", "test"], required=True)
    parser.add_argument("--output", type=Path, required=True, help="sanitized aggregate JSON")
    parser.add_argument("--offline-fake", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = RunConfig.load(args.config)
    bundle = validate_bundle(args.bundle, require_formal=True)
    team = json.loads(args.team.read_text(encoding="utf-8"))
    prompts = tuple(team.get("prompts", []))
    if team.get("bundle_hash") != bundle.overall_hash or team.get("frozen") is not True:
        raise RuntimeError("frozen team identity mismatch")
    if not args.offline_fake:
        raise RuntimeError("stage-one evaluator requires --offline-fake; real evaluation is not authorized")
    split = SplitName(args.split)
    access = SplitAccessController(formal=config.stage == "formal")
    access.freeze([prompt_hash(prompt) for prompt in prompts])
    accounting_budget = BudgetLedger(len(bundle.splits[split.value]) * 5, member_count=5)
    provider_accounting = ProviderAccounting()
    parser = StrictAnswerParser(bundle.parser_contract)

    def factory(member_id: int) -> MemberEvaluator:
        provider = OpenAICompatibleProvider(
            task_model=config.task_model,
            reflection_model=config.reflection_model,
            transport=DeterministicFakeTransport(),
            temperature=0.0,
            max_tokens=64,
            timeout_seconds=10.0,
            max_retries=0,
            accounting=provider_accounting,
            pricing_per_million_tokens=bundle.model_contract.get(
                "pricing_per_million_tokens", {}
            ),
        )
        return MemberEvaluator(member_id=member_id, provider=provider, parser=parser, budget=accounting_budget)

    evaluator = FinalTeamEvaluator(prompts=prompts, evaluator_factory=factory, access=access)
    started = time.monotonic()
    summary, _ = evaluator.evaluate(
        split=split,
        examples=bundle.splits[split.value],
        initial_member_accuracies=initial_accuracies_from_bundle(bundle.manifest, split),
    )
    summary["bundle_hash"] = bundle.overall_hash
    summary["prompt_hashes"] = [prompt_hash(prompt) for prompt in prompts]
    summary["logical_evaluations"] = accounting_budget.snapshot()
    summary["provider_accounting"] = provider_accounting.snapshot()
    summary["wall_clock_seconds"] = time.monotonic() - started
    write_canonical_json(args.output, summary)
    require_clean_public_artifacts([args.output])
    print(f"PASS {split.value} aggregate evaluation")


if __name__ == "__main__":
    main()
