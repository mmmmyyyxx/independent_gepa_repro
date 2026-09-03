from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path

from _bootstrap import ROOT

from independent_gepa.artifacts import write_private_json
from independent_gepa.audit import require_clean_public_artifacts
from independent_gepa.budget import BudgetLedger
from independent_gepa.bundle import canonical_json_bytes, prompt_hash, sha256_bytes, validate_bundle, write_canonical_json
from independent_gepa.evaluator import MemberEvaluator
from independent_gepa.parser import StrictAnswerParser
from independent_gepa.provider import ExactRequestCache, OpenAICompatibleProvider, ProviderAccounting
from independent_gepa.runner import RunConfig, assert_model_routing_matches_bundle
from independent_gepa.testing import DeterministicFakeTransport
from independent_gepa.v17 import INITIAL_PARITY_POLICY_VERSION, initial_parity_passes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify V17 shared-initial-state parity")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "independent_gepa.yaml")
    parser.add_argument("--private-run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline-fake", action="store_true")
    parser.add_argument("--allow-real-api", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.offline_fake == args.allow_real_api:
        raise RuntimeError("select exactly one of --offline-fake or --allow-real-api")
    config = RunConfig.load(args.config)
    bundle = validate_bundle(args.bundle, require_formal=True, stage=None)
    assert_model_routing_matches_bundle(config, bundle)
    if len(set(prompt_hash(prompt) for prompt in bundle.prompts)) != 1:
        raise RuntimeError("initial prompts are not shared-identical")
    examples = bundle.splits["optimization"]
    logical = BudgetLedger(len(examples) * 5, member_count=5)
    accounting = ProviderAccounting()
    cache = ExactRequestCache(args.private_run_dir / "exact_request_cache.json")
    provider_cfg = dict(config.raw["provider"])
    common = {
        "task_model": config.task_model,
        "reflection_model": config.reflection_model,
        "temperature": float(provider_cfg["temperature"]),
        "max_tokens": int(provider_cfg["max_tokens"]),
        "timeout_seconds": float(provider_cfg["timeout_seconds"]),
        "max_retries": int(provider_cfg["max_retries"]),
        "enable_thinking": bool(provider_cfg["enable_thinking"]),
        "cache": cache,
        "accounting": accounting,
        "pricing_per_million_tokens": bundle.model_contract.get("pricing_per_million_tokens", {}),
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
    parser = StrictAnswerParser(bundle.parser_contract)
    started = time.monotonic()
    rows = []
    for member_id, prompt in enumerate(bundle.prompts):
        evaluator = MemberEvaluator(
            member_id=member_id,
            provider=provider,
            parser=parser,
            budget=logical,
            concurrency=config.evaluation_concurrency,
        )
        rows.append(evaluator.evaluate(prompt, examples))
    vectors = [
        [item.parsed_option if item.valid else None for item in member_rows]
        for member_rows in rows
    ]
    vector_hashes = [sha256_bytes(canonical_json_bytes(vector)) for vector in vectors]
    correct_counts = [sum(item.correct for item in member_rows) for member_rows in rows]
    expected = bundle.manifest["initial_metrics"]["optimization"]
    # Bundle validation fixes every request identity. The online gate verifies that
    # the five identical members behave identically in this canonical evaluation;
    # historical outcomes remain diagnostics and are never resampled/cherry-picked.
    reference_vector_match = vector_hashes[0] == expected["parsed_answer_vector_hash"]
    reference_score_match = (
        correct_counts == list(expected["member_correct"])
        and correct_counts[0] == int(expected["team_correct"])
    )
    parity = initial_parity_passes(correct_counts, vector_hashes)
    write_private_json(
        args.private_run_dir / "initial_parity_private.json",
        {
            "bundle_hash": bundle.overall_hash,
            "outputs": [[item.output_record() for item in member_rows] for member_rows in rows],
        },
    )
    summary = {
        "artifact_schema_version": "v17_initial_parity_v1",
        "bundle_hash": bundle.overall_hash,
        "experiment_seed": bundle.experiment_seed,
        "prompt_hash": prompt_hash(bundle.prompts[0]),
        "member_correct": correct_counts,
        "team_correct": correct_counts[0],
        "parsed_answer_vector_hashes": vector_hashes,
        "expected_parsed_answer_vector_hash": expected["parsed_answer_vector_hash"],
        "reference_vector_match": reference_vector_match,
        "reference_score_match": reference_score_match,
        "parity_policy_version": INITIAL_PARITY_POLICY_VERSION,
        "logical_evaluations": logical.snapshot(),
        "provider_accounting": accounting.snapshot(),
        "wall_clock_seconds": time.monotonic() - started,
        "parity_status": "PASS" if parity else "HOLD",
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_canonical_json(args.output, summary)
    require_clean_public_artifacts([args.output])
    if not parity:
        raise RuntimeError("initial-state parity mismatch; expensive GEPA search is forbidden")
    print(f"PASS initial-state parity seed={bundle.experiment_seed}")


if __name__ == "__main__":
    main()
