from __future__ import annotations

import json
from pathlib import Path

import pytest

from independent_gepa.audit import audit_value
from independent_gepa.bundle import validate_bundle
from independent_gepa.provider import ExactRequestCache, OpenAICompatibleProvider
from independent_gepa.protocol import ProtocolViolation
from independent_gepa.runner import (
    IndependentRunner,
    MemberOptimizationResult,
    RealGEPAExecutor,
    RunConfig,
)
from independent_gepa.testing import DeterministicFakeTransport
from tests.helpers import make_bundle, write_run_config


class DirectBestExecutor:
    def optimize(
        self,
        *,
        member_id,
        seed_prompt,
        optimization_examples,
        adapter,
        provider,
        settings,
        run_dir,
        gepa_seed,
        member_budget,
        token_budget_policy,
    ):
        return MemberOptimizationResult(
            member_id=member_id,
            gepa_seed=gepa_seed,
            best_prompt=f"{seed_prompt} :: independent-best-{member_id}",
            candidate_count=member_id + 1,
            logical_evaluations=0,
        )


def _factory(config: RunConfig, transports: list[DeterministicFakeTransport]):
    def factory(member_id, run_dir, accounting, token_budget_policy):
        transport = DeterministicFakeTransport()
        transports.append(transport)
        return OpenAICompatibleProvider(
            task_model=config.task_model,
            reflection_model=config.reflection_model,
            transport=transport,
            temperature=0,
            max_tokens=128,
            timeout_seconds=2,
            max_retries=0,
            cache=ExactRequestCache(run_dir / "exact_request_cache.json"),
            accounting=accounting,
            token_budget_policy=token_budget_policy,
        )

    return factory


def test_direct_final_composition_and_member_run_isolation(tmp_path) -> None:
    bundle = validate_bundle(make_bundle(tmp_path / "input"), require_formal=False)
    config = RunConfig.load(write_run_config(tmp_path / "config.yaml"))
    transports: list[DeterministicFakeTransport] = []
    output = tmp_path / "runs" / "direct"
    prompts, summary = IndependentRunner(
        bundle=bundle,
        config=config,
        output_root=output,
        provider_factory=_factory(config, transports),
        executor=DirectBestExecutor(),
    ).run()
    assert prompts == tuple(
        f"identical initial prompt :: independent-best-{index}" for index in range(5)
    )
    assert len(transports) == 5
    assert len({id(item) for item in transports}) == 5
    assert [path.name for path in sorted(output.glob("member_*"))] == [
        f"member_{index}" for index in range(5)
    ]
    private = json.loads((output / "final_team_private.json").read_text(encoding="utf-8"))
    assert private["prompts"] == list(prompts)
    assert "combinations" not in str(summary).lower()
    assert not audit_value(summary)


def test_checkpoint_identity_mismatch_is_rejected(tmp_path) -> None:
    bundle = validate_bundle(make_bundle(tmp_path / "input"), require_formal=False)
    config = RunConfig.load(write_run_config(tmp_path / "config.yaml"))
    output = tmp_path / "runs" / "resume"
    IndependentRunner(
        bundle=bundle,
        config=config,
        output_root=output,
        provider_factory=_factory(config, []),
        executor=DirectBestExecutor(),
    ).run()
    identity = output / "member_0" / "checkpoint_identity.json"
    row = json.loads(identity.read_text(encoding="utf-8"))
    row["bundle_hash"] = "wrong"
    identity.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(ProtocolViolation, match="checkpoint identity mismatch"):
        IndependentRunner(
            bundle=bundle,
            config=config,
            output_root=output,
            provider_factory=_factory(config, []),
            executor=DirectBestExecutor(),
        ).run()


def test_fake_five_member_end_to_end_uses_actual_gepa_api(tmp_path) -> None:
    bundle = validate_bundle(
        make_bundle(tmp_path / "input", sizes=(3, 2, 2), total_budget=50),
        require_formal=False,
    )
    config = RunConfig.load(write_run_config(tmp_path / "config.yaml"))
    transports: list[DeterministicFakeTransport] = []
    output = tmp_path / "runs" / "gepa"
    prompts, summary = IndependentRunner(
        bundle=bundle,
        config=config,
        output_root=output,
        provider_factory=_factory(config, transports),
        executor=RealGEPAExecutor(),
    ).run()
    assert len(prompts) == 5
    assert all("unambiguous" in prompt.lower() for prompt in prompts)
    assert all(row["candidate_count"] >= 2 for row in summary["members"])
    assert summary["budget"]["consumed_total"] <= summary["budget"]["allocated_total"]
    assert summary["provider_accounting"]["roles"]["reflection"]["logical_calls"] >= 5
    resumed_prompts, resumed_summary = IndependentRunner(
        bundle=bundle,
        config=config,
        output_root=output,
        provider_factory=_factory(config, transports),
        executor=RealGEPAExecutor(),
    ).run()
    assert resumed_prompts == prompts
    assert resumed_summary["budget"]["consumed_total"] == summary["budget"]["consumed_total"]
    assert resumed_summary["provider_accounting"] == summary["provider_accounting"]
