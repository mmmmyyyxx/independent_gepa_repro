from __future__ import annotations

from pathlib import Path

import pytest

from independent_gepa.evaluator import solver_system_prompt
from independent_gepa.protocol import BudgetExceeded, Example, ProtocolViolation
from independent_gepa.provider import (
    OpenAICompatibleProvider,
    ProviderAccounting,
    ProviderResponse,
    TokenBudgetPolicy,
)
from independent_gepa.runner import RunConfig, derive_gepa_seed
from independent_gepa.v17 import build_v17_export_spec


REFERENCE = Path(__file__).resolve().parents[2] / "multi_agent_diversity"


def test_v17_frozen_source_imports_config_prompts_splits_and_budgets() -> None:
    expected = {56: (526935, 1793, 50), 57: (493420, 1790, 51), 58: (620887, 1869, 50)}
    for seed, (tokens, calls, initial_correct) in expected.items():
        spec = build_v17_export_spec(REFERENCE, seed)
        model = spec["model_contract"]["inline"]
        formal = spec["budget_reference"]["inline"]["formal"]
        assert model["shared_task_model"]["model"] == "qwen3-14b"
        assert model["independent_gepa_reflection_model"]["model"] == "qwen3-14b"
        assert formal["reference_training_tokens"] == tokens
        assert formal["reference_provider_calls"] == calls
        assert spec["initial_metrics"]["optimization"]["member_correct"] == [initial_correct] * 5
        assert len({(row["path"], row["index"]) for row in spec["initial_prompts"]}) == 5


def test_v17_task_request_rendering_matches_fixed_contract() -> None:
    example = Example("x", "Who is meant?", ("one", "two", "three"), "A")
    assert example.task_input() == "Who is meant?\nOptions:\n(A) one\n(B) two\n(C) three"
    rendered = solver_system_prompt("Reason carefully.")
    assert rendered.startswith("Follow the decision procedure below.\n\nDecision procedure:")
    assert "Decision procedure:\nReason carefully." in rendered
    assert rendered.endswith("There must be exactly one FINAL_ANSWER line.")


def test_v17_formal_config_and_deterministic_gepa_seed() -> None:
    config = RunConfig.load(Path(__file__).resolve().parents[1] / "configs" / "independent_gepa.yaml")
    assert config.task_model == config.reflection_model == "qwen3-14b"
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
        task_model="qwen3-14b",
        reflection_model="qwen3-14b",
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
