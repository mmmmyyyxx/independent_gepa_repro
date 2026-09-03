from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from independent_gepa.budget import BudgetLedger
from independent_gepa.evaluator import MemberEvaluator
from independent_gepa.parser import StrictAnswerParser
from independent_gepa.protocol import BudgetExceeded, Example, OperationalFailure, ProtocolViolation
from independent_gepa.provider import (
    ExactRequestCache,
    OpenAICompatibleProvider,
    ProviderHTTPError,
    ProviderResponse,
)
from independent_gepa.testing import DeterministicFakeTransport
from tests.helpers import parser_contract


def _provider(transport, cache=None) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        task_model="task-fixed",
        reflection_model="reflection-fixed",
        transport=transport,
        temperature=0.0,
        max_tokens=32,
        timeout_seconds=1.0,
        max_retries=2,
        cache=cache,
    )


def test_equal_floor_budget_and_overrun() -> None:
    ledger = BudgetLedger(12, member_count=5)
    assert ledger.member_budget == 2
    assert ledger.unallocated_remainder == 2
    ledger.consume(0, 2)
    with pytest.raises(BudgetExceeded):
        ledger.consume(0)


def test_budget_ledger_persists_and_rejects_resume_identity_mismatch(tmp_path) -> None:
    state = tmp_path / "runs" / "member_0" / "logical_budget_ledger.json"
    first = BudgetLedger(20, member_count=5, state_paths={0: state})
    first.consume(0, 3)
    resumed = BudgetLedger(20, member_count=5, state_paths={0: state})
    assert resumed.consumed_by_member[0] == 3
    with pytest.raises(ProtocolViolation, match="identity mismatch"):
        BudgetLedger(25, member_count=5, state_paths={0: state})


def test_exact_cache_counts_logical_calls_not_real_requests(tmp_path) -> None:
    transport = DeterministicFakeTransport()
    provider = _provider(transport, ExactRequestCache(tmp_path / "runs" / "cache.json"))
    messages = [
        {"role": "system", "content": "prompt"},
        {"role": "user", "content": "Question [gold=A]"},
    ]
    first, first_hit = provider.complete("task", messages)
    second, second_hit = provider.complete("task", messages)
    usage = provider.accounting.role("task")
    assert first == second
    assert not first_hit and second_hit
    assert usage.logical_calls == 2
    assert usage.real_requests == 1
    assert usage.cache_hits == 1
    assert usage.total_tokens == first.total_tokens


def test_transient_only_retry_policy() -> None:
    attempts = 0

    def transient(_request):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ProviderHTTPError(429)
        return ProviderResponse("A", "stop", 1, 1)

    provider = _provider(transient)
    assert provider.complete("task", [{"role": "user", "content": "x"}])[0].text == "A"
    assert attempts == 3

    failed_attempts = 0

    def non_transient(_request):
        nonlocal failed_attempts
        failed_attempts += 1
        raise ProviderHTTPError(401)

    provider = _provider(non_transient)
    with pytest.raises(OperationalFailure):
        provider.complete("task", [{"role": "user", "content": "x"}])
    assert failed_attempts == 1


def test_operational_failure_is_not_score_zero() -> None:
    def broken(_request):
        raise ValueError("schema")

    provider = _provider(broken)
    ledger = BudgetLedger(5, member_count=5)
    evaluator = MemberEvaluator(
        member_id=0,
        provider=provider,
        parser=StrictAnswerParser(parser_contract()),
        budget=ledger,
    )
    example = Example("x", "Question", ("a", "b", "c"), "A")
    with pytest.raises(OperationalFailure):
        evaluator.evaluate_one("prompt", example)
    assert ledger.consumed_by_member[0] == 1


def test_real_transport_requires_double_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("KEY", "secret")
    monkeypatch.setenv("URL", "https://example.invalid")
    with pytest.raises(ProtocolViolation, match="config and CLI"):
        OpenAICompatibleProvider.from_environment(
            task_model="x",
            reflection_model="x",
            api_key_env="KEY",
            base_url_env="URL",
            config_allows_real_api=False,
            cli_allows_real_api=True,
            temperature=0,
            max_tokens=1,
            timeout_seconds=1,
            max_retries=0,
        )


def test_provider_repr_never_contains_credentials() -> None:
    provider = _provider(DeterministicFakeTransport())
    assert "key" not in repr(provider).lower()
    assert "base_url" not in repr(provider).lower()
    assert provider.accounting.snapshot()["estimated_cost"] is None
    assert provider.accounting.snapshot()["cost_status"] == "unavailable_missing_bundle_pricing"


def test_split_model_request_routing_and_solver_thinking_disabled() -> None:
    provider = OpenAICompatibleProvider(
        task_model="qwen3-8b",
        reflection_model="qwen3.7-flash",
        transport=DeterministicFakeTransport(),
        temperature=0.0,
        max_tokens=1800,
        timeout_seconds=120.0,
        max_retries=3,
        enable_thinking=False,
    )
    task = provider.request_payload("task", [{"role": "user", "content": "x"}])
    reflection = provider.request_payload("reflection", [{"role": "user", "content": "x"}])
    assert task["model"] == "qwen3-8b"
    assert task["extra_body"] == {"enable_thinking": False}
    assert reflection["model"] == "qwen3.7-flash"
    assert reflection["extra_body"] == {"enable_thinking": False}


def test_exact_cache_concurrent_atomic_persistence(tmp_path) -> None:
    path = tmp_path / "runs" / "cache.json"
    cache = ExactRequestCache(path)

    def write(index: int) -> None:
        cache.put(
            {"index": index},
            ProviderResponse(
                text=str(index),
                finish_reason="stop",
                prompt_tokens=1,
                completion_tokens=1,
            ),
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write, range(40)))
    assert len(json.loads(path.read_text(encoding="utf-8"))) == 40


def test_budget_ledger_concurrent_atomic_persistence(tmp_path) -> None:
    path = tmp_path / "runs" / "ledger.json"
    ledger = BudgetLedger(250, member_count=5, state_paths={0: path})
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _index: ledger.consume(0), range(40)))
    restored = BudgetLedger(250, member_count=5, state_paths={0: path})
    assert restored.consumed_by_member[0] == 40
