from __future__ import annotations

import argparse
from pathlib import Path

from _bootstrap import ROOT

from independent_gepa.artifacts import write_private_json
from independent_gepa.audit import require_clean_public_artifacts
from independent_gepa.provider import ExactRequestCache, OpenAICompatibleProvider
from independent_gepa.runner import (
    IndependentRunner,
    RealGEPAExecutor,
    load_validated_inputs,
)
from independent_gepa.testing import DeterministicFakeTransport
from independent_gepa.bundle import write_canonical_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run five independent GEPA member searches")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "independent_gepa.yaml")
    parser.add_argument("--output", type=Path, required=True, help="private ignored runs directory")
    parser.add_argument("--public-summary", type=Path)
    parser.add_argument("--offline-fake", action="store_true")
    parser.add_argument("--allow-real-api", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.offline_fake == args.allow_real_api:
        raise RuntimeError("select exactly one of --offline-fake or --allow-real-api")
    bundle, config = load_validated_inputs(args.bundle, args.config)
    provider_cfg = dict(config.raw["provider"])

    def factory(member_id: int, run_dir: Path, accounting):
        common = {
            "task_model": config.task_model,
            "reflection_model": config.reflection_model,
            "temperature": float(provider_cfg["temperature"]),
            "max_tokens": int(provider_cfg["max_tokens"]),
            "timeout_seconds": float(provider_cfg["timeout_seconds"]),
            "max_retries": int(provider_cfg["max_retries"]),
            "enable_thinking": bool(provider_cfg["enable_thinking"]),
            "cache": ExactRequestCache(run_dir / "exact_request_cache.json"),
            "accounting": accounting,
            "pricing_per_million_tokens": bundle.model_contract.get(
                "pricing_per_million_tokens", {}
            ),
        }
        if args.offline_fake:
            return OpenAICompatibleProvider(transport=DeterministicFakeTransport(), **common)
        return OpenAICompatibleProvider.from_environment(
            api_key_env=str(provider_cfg["api_key_env"]),
            base_url_env=str(provider_cfg["base_url_env"]),
            config_allows_real_api=config.real_api_allowed,
            cli_allows_real_api=args.allow_real_api,
            **common,
        )

    runner = IndependentRunner(
        bundle=bundle,
        config=config,
        output_root=args.output,
        provider_factory=factory,
        executor=RealGEPAExecutor(),
    )
    prompts, summary = runner.run()
    if args.public_summary is not None:
        write_canonical_json(args.public_summary, summary)
        require_clean_public_artifacts([args.public_summary])
    outcome = "frozen independent team" if len(prompts) == 5 else "member-0 canary"
    print(f"PASS {outcome} bundle={bundle.overall_hash}")


if __name__ == "__main__":
    main()
