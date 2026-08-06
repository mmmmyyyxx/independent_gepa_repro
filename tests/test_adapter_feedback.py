from __future__ import annotations

import pytest

from independent_gepa.adapter import IndependentGEPAAdapter
from independent_gepa.budget import BudgetLedger
from independent_gepa.evaluator import MemberEvaluator
from independent_gepa.feedback import assert_feedback_isolation
from independent_gepa.parser import StrictAnswerParser
from independent_gepa.protocol import Example, ProtocolViolation
from independent_gepa.provider import OpenAICompatibleProvider
from independent_gepa.testing import DeterministicFakeTransport
from tests.helpers import parser_contract


def _adapter(member_id: int = 0) -> IndependentGEPAAdapter:
    provider = OpenAICompatibleProvider(
        task_model="task",
        reflection_model="reflection",
        transport=DeterministicFakeTransport(),
        temperature=0,
        max_tokens=32,
        timeout_seconds=1,
        max_retries=0,
    )
    evaluator = MemberEvaluator(
        member_id=member_id,
        provider=provider,
        parser=StrictAnswerParser(parser_contract()),
        budget=BudgetLedger(20, member_count=5),
    )
    return IndependentGEPAAdapter(member_id, evaluator)


def test_adapter_scores_and_current_member_trace_only() -> None:
    adapter = _adapter()
    example = Example("x", "Question [gold=A]", ("a", "b", "c"), "A")
    seed = adapter.evaluate([example], {"system_prompt": "initial"}, capture_traces=True)
    improved = adapter.evaluate(
        [example],
        {"system_prompt": "return one unambiguous answer"},
        capture_traces=True,
    )
    assert seed.scores == [0.0]
    assert improved.scores == [1.0]
    assert improved.trajectories is not None
    assert improved.trajectories[0].member_id == 0
    reflective = adapter.make_reflective_dataset(
        {"system_prompt": "return one unambiguous answer"},
        improved,
        ["system_prompt"],
    )
    assert set(reflective) == {"system_prompt"}
    assert "Current Member Response" in reflective["system_prompt"][0]
    assert_feedback_isolation(reflective)


def test_adapter_rejects_extra_candidate_component() -> None:
    adapter = _adapter()
    with pytest.raises(ProtocolViolation, match="exactly one"):
        adapter.evaluate([], {"system_prompt": "x", "peer_prompt": "y"})


def test_recursive_feedback_leakage_detection() -> None:
    with pytest.raises(ProtocolViolation, match="forbidden"):
        assert_feedback_isolation({"safe": [{"nested": {"peer_answer": "A"}}]})
    with pytest.raises(ProtocolViolation, match="forbidden"):
        assert_feedback_isolation({"diagnostics": {"G": 3}})


def test_cross_member_trajectory_is_rejected() -> None:
    first = _adapter(0)
    second = _adapter(1)
    example = Example("x", "Question [gold=A]", ("a", "b", "c"), "A")
    batch = first.evaluate([example], {"system_prompt": "initial"}, capture_traces=True)
    with pytest.raises(ProtocolViolation, match="cross-member"):
        second.make_reflective_dataset({"system_prompt": "initial"}, batch, ["system_prompt"])
