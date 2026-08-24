from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from _bootstrap import ROOT

from independent_gepa.artifacts import write_private_json
from independent_gepa.audit import require_clean_public_artifacts
from independent_gepa.budget import BudgetLedger
from independent_gepa.bundle import prompt_hash, validate_bundle, write_canonical_json
from independent_gepa.evaluator import MemberEvaluator
from independent_gepa.final_evaluator import FinalTeamEvaluator, initial_accuracies_from_bundle
from independent_gepa.parser import StrictAnswerParser
from independent_gepa.protocol import SplitAccessController, SplitName
from independent_gepa.provider import ExactRequestCache, OpenAICompatibleProvider, ProviderAccounting
from independent_gepa.runner import RunConfig
from independent_gepa.testing import DeterministicFakeTransport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate one frozen five-prompt team")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "independent_gepa.yaml")
    parser.add_argument("--team", type=Path, required=True, help="private frozen-team JSON")
    parser.add_argument("--split", choices=["development", "test"], required=True)
    parser.add_argument("--output", type=Path, required=True, help="sanitized aggregate JSON")
    parser.add_argument("--private-run-dir", type=Path, required=True)
    parser.add_argument(
        "--lifecycle-state",
        type=Path,
        required=True,
        help="private per-seed seal enforcing development-before-test and one evaluation each",
    )
    parser.add_argument("--offline-fake", action="store_true")
    parser.add_argument("--allow-real-api", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.offline_fake == args.allow_real_api:
        raise RuntimeError("select exactly one of --offline-fake or --allow-real-api")
    config = RunConfig.load(args.config)
    bundle = validate_bundle(args.bundle, require_formal=True, stage=config.stage)
    team = json.loads(args.team.read_text(encoding="utf-8"))
    prompts = tuple(team.get("prompts", []))
    if team.get("bundle_hash") != bundle.overall_hash or team.get("frozen") is not True:
        raise RuntimeError("frozen team identity mismatch")
    team_hashes = [prompt_hash(prompt) for prompt in prompts]
    lifecycle = {}
    if args.lifecycle_state.exists():
        lifecycle = json.loads(args.lifecycle_state.read_text(encoding="utf-8"))
        if lifecycle.get("bundle_hash") != bundle.overall_hash or lifecycle.get("prompt_hashes") != team_hashes:
            raise RuntimeError("evaluation lifecycle identity mismatch")
    if args.split == "development" and lifecycle:
        raise RuntimeError("development has already been evaluated for this frozen team")
    if args.split == "test" and lifecycle.get("development_status") != "complete":
        raise RuntimeError("test is forbidden until development evaluation is complete")
    if args.split == "test" and lifecycle.get("test_status") == "complete":
        raise RuntimeError("test has already been evaluated for this frozen team")
    split = SplitName(args.split)
    access = SplitAccessController(formal=config.stage == "formal")
    access.freeze(team_hashes)
    accounting_budget = BudgetLedger(len(bundle.splits[split.value]) * 5, member_count=5)
    provider_accounting = ProviderAccounting()
    shared_cache = ExactRequestCache(args.private_run_dir / "exact_request_cache.json")
    parser = StrictAnswerParser(bundle.parser_contract)

    def factory(member_id: int) -> MemberEvaluator:
        provider_cfg = dict(config.raw["provider"])
        common = {
            "task_model": config.task_model,
            "reflection_model": config.reflection_model,
            "temperature": float(provider_cfg["temperature"]),
            "max_tokens": int(provider_cfg["max_tokens"]),
            "timeout_seconds": float(provider_cfg["timeout_seconds"]),
            "max_retries": int(provider_cfg["max_retries"]),
            "enable_thinking": bool(provider_cfg["enable_thinking"]),
            "cache": shared_cache,
            "accounting": provider_accounting,
            "pricing_per_million_tokens": bundle.model_contract.get(
                "pricing_per_million_tokens", {}
            ),
        }
        if args.offline_fake:
            provider = OpenAICompatibleProvider(transport=DeterministicFakeTransport(), **common)
        else:
            provider = OpenAICompatibleProvider.from_environment(
                api_key_env=str(provider_cfg["api_key_env"]),
                base_url_env=str(provider_cfg["base_url_env"]),
                config_allows_real_api=config.real_api_allowed,
                cli_allows_real_api=args.allow_real_api,
                **common,
            )
        return MemberEvaluator(
            member_id=member_id,
            provider=provider,
            parser=parser,
            budget=accounting_budget,
            concurrency=config.evaluation_concurrency,
        )

    evaluator = FinalTeamEvaluator(prompts=prompts, evaluator_factory=factory, access=access)
    started = time.monotonic()
    summary, diagnostics = evaluator.evaluate(
        split=split,
        examples=bundle.splits[split.value],
        initial_member_accuracies=initial_accuracies_from_bundle(bundle.manifest, split),
    )
    summary["bundle_hash"] = bundle.overall_hash
    summary["prompt_hashes"] = team_hashes
    summary["logical_evaluations"] = accounting_budget.snapshot()
    summary["provider_accounting"] = provider_accounting.snapshot()
    summary["wall_clock_seconds"] = time.monotonic() - started
    summary["evaluation_interpretation"] = (
        "frozen-split test evaluation" if split is SplitName.TEST else "post-search validation audit"
    )
    summary["evaluated_at_utc"] = datetime.now(timezone.utc).isoformat()
    summary["split_access_log"] = list(access.accesses)
    write_private_json(
        args.private_run_dir / "diagnostics_private.json",
        {"split": split.value, "diagnostics": [row.__dict__ for row in diagnostics]},
    )
    write_canonical_json(args.output, summary)
    require_clean_public_artifacts([args.output])
    lifecycle.update(
        {
            "bundle_hash": bundle.overall_hash,
            "prompt_hashes": team_hashes,
            f"{args.split}_status": "complete",
            f"{args.split}_evaluated_at_utc": summary["evaluated_at_utc"],
            f"{args.split}_summary_sha256": __import__("hashlib").sha256(
                args.output.read_bytes()
            ).hexdigest(),
        }
    )
    write_private_json(args.lifecycle_state, lifecycle)
    print(f"PASS {split.value} aggregate evaluation")


if __name__ == "__main__":
    main()
