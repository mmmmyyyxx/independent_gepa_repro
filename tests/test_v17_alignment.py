from __future__ import annotations

from pathlib import Path

import pytest

from independent_gepa.bundle import read_json, sha256_file, validate_bundle
from independent_gepa.evaluator import solver_system_prompt
from independent_gepa.model_profile import split_role_model_contract
from independent_gepa.model_variant import export_model_variant_bundle
from independent_gepa.protocol import BudgetExceeded, Example, ProtocolViolation
from independent_gepa.provider import (
    OpenAICompatibleProvider,
    ProviderAccounting,
    ProviderResponse,
    TokenBudgetPolicy,
)
from independent_gepa.runner import RunConfig, derive_gepa_seed
from independent_gepa.v17 import initial_parity_passes

from .helpers import make_bundle


def test_initial_parity_policy_uses_current_same_run_vector_not_historical_score() -> None:
    assert initial_parity_passes([50] * 5, ["current"] * 5)
    assert not initial_parity_passes([50] * 5, ["a", "a", "a", "a", "b"])


def test_split_role_model_profile_keeps_transport_settings_fixed() -> None:
    model = split_role_model_contract()
    task = model["shared_task_model"]
    assert task["model"] == "qwen3-8b"
    assert task["enable_thinking"] is False
    for role in (
        "independent_gepa_evaluator_model",
        "independent_gepa_optimizer_model",
        "independent_gepa_reflection_model",
    ):
        assert model[role]["model"] == "qwen3.7-flash"
        assert model[role]["enable_thinking"] is False
    for role in ("independent_gepa_optimizer_model", "independent_gepa_reflection_model"):
        assert model[role]["temperature"] == 0.0
        assert model[role]["max_tokens"] == 1800
        assert model[role]["timeout_seconds"] == 120.0
        assert model[role]["max_retries"] == 3


def test_model_variant_changes_models_only_and_invalidates_old_initial_metrics(tmp_path) -> None:
    source_path = make_bundle(
        tmp_path / "source", sizes=(75, 50, 125), experiment_seed=56
    )
    source = validate_bundle(source_path, require_formal=True)
    output = tmp_path / "variant"
    export_model_variant_bundle(source_path, output)
    variant = validate_bundle(output, require_formal=True)

    assert variant.model_contract["shared_task_model"]["model"] == "qwen3-8b"
    assert variant.model_contract["independent_gepa_reflection_model"]["model"] == "qwen3.7-flash"
    assert variant.prompts == source.prompts
    assert variant.manifest["split_hashes"] == source.manifest["split_hashes"]
    assert read_json(output / "budget_reference.json") == read_json(source_path / "budget_reference.json")
    assert read_json(output / "parser_contract.json") == read_json(source_path / "parser_contract.json")
    assert read_json(output / "reference_results.json") == read_json(source_path / "reference_results.json")
    assert variant.manifest["initial_metrics"] == {
        name: {"status": "not_evaluated"}
        for name in ("optimization", "development", "test")
    }
    for member_id in range(5):
        relative = Path("initialization") / f"agent_{member_id}.txt"
        assert sha256_file(output / relative) == sha256_file(source_path / relative)


def test_v17_task_request_rendering_matches_fixed_contract() -> None:
    example = Example("x", "Who is meant?", ("one", "two", "three"), "A")
    assert example.task_input() == "Who is meant?\nOptions:\n(A) one\n(B) two\n(C) three"
    rendered = solver_system_prompt("Reason carefully.")
    assert rendered.startswith("Follow the decision procedure below.\n\nDecision procedure:")
    assert "Decision procedure:\nReason carefully." in rendered
    assert rendered.endswith("There must be exactly one FINAL_ANSWER line.")


def test_v17_formal_config_and_deterministic_gepa_seed() -> None:
    config = RunConfig.load(Path(__file__).resolve().parents[1] / "configs" / "independent_gepa.yaml")
    assert config.task_model == "qwen3-8b"
    assert config.evaluator_model == "qwen3.7-flash"
    assert config.optimizer_model == "qwen3.7-flash"
    assert config.reflection_model == "qwen3.7-flash"
    assert config.raw["formal_seeds"] == [56, 57, 58]
    assert [derive_gepa_seed(57, member) for member in range(5)] == [57000, 57001, 57002, 57003, 57004]
    with pytest.raises(ProtocolViolation):
        derive_gepa_seed(46, 0)


def test_persistent_provider_accounting_and_hard_token_stop(tmp_path) -> None:
    state = tmp_path / "runs" / "member_0" / "provider_accounting.json"
    accounting = ProviderAccounting(state_path=state, identity="frozen")

    def transport(_request):
        return ProviderResponse("FINAL_ANSWER: A", "stop", 1, 1)

    provider = OpenAICompatibleProvider(
        task_model="qwen3-8b",
        reflection_model="qwen3.7-flash",
        transport=transport,
        temperature=0,
        max_tokens=10,
        timeout_seconds=1,
        max_retries=0,
        accounting=accounting,
        token_budget_policy=TokenBudgetPolicy(5, 6, 1),
    )
    provider.complete("task", [{"role": "user", "content": "one"}])
    provider.complete("reflection", [{"role": "user", "content": "two"}])
    provider.complete("task", [{"role": "user", "content": "three"}])
    with pytest.raises(BudgetExceeded, match="target reached"):
        provider.complete("task", [{"role": "user", "content": "four"}])
    restored = ProviderAccounting(state_path=state, identity="frozen")
    snapshot = restored.snapshot()
    assert snapshot["total_tokens"] == 6
    assert snapshot["roles"]["task"]["real_requests"] == 2
    assert snapshot["roles"]["reflection"]["real_requests"] == 1
    with pytest.raises(ProtocolViolation, match="identity mismatch"):
        ProviderAccounting(state_path=state, identity="different")
