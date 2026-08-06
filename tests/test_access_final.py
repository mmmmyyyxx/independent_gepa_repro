from __future__ import annotations

import pytest

from independent_gepa.budget import BudgetLedger
from independent_gepa.evaluator import MemberEvaluator
from independent_gepa.final_evaluator import FinalTeamEvaluator, plurality
from independent_gepa.parser import StrictAnswerParser
from independent_gepa.protocol import Example, ProtocolViolation, SplitAccessController, SplitName
from independent_gepa.provider import OpenAICompatibleProvider
from independent_gepa.testing import DeterministicFakeTransport
from tests.helpers import parser_contract


def test_split_access_lifecycle_and_one_time_rules() -> None:
    access = SplitAccessController(formal=True)
    with pytest.raises(ProtocolViolation, match="optimization"):
        access.access_for_optimization(SplitName.DEVELOPMENT)
    with pytest.raises(ProtocolViolation, match="frozen"):
        access.access_for_final_evaluation(SplitName.TEST)
    access.access_for_optimization(SplitName.OPTIMIZATION)
    access.freeze(["a", "b", "c", "d", "e"])
    access.access_for_final_evaluation(SplitName.DEVELOPMENT)
    with pytest.raises(ProtocolViolation, match="at most once"):
        access.access_for_final_evaluation(SplitName.DEVELOPMENT)
    access.access_for_final_evaluation(SplitName.TEST)
    with pytest.raises(ProtocolViolation, match="at most once"):
        access.access_for_final_evaluation(SplitName.TEST)


def test_nonformal_test_access_is_forbidden() -> None:
    access = SplitAccessController(formal=False)
    access.freeze(["a", "b", "c", "d", "e"])
    with pytest.raises(ProtocolViolation, match="formal"):
        access.access_for_final_evaluation(SplitName.TEST)


def test_plurality_tie_abstains() -> None:
    assert plurality(["A", "A", "B", None, "C"]) == ("A", False)
    assert plurality(["A", "A", "B", "B", None]) == (None, True)
    assert plurality([None] * 5) == (None, True)


def test_final_team_metrics_use_five_frozen_prompts() -> None:
    examples = [
        Example("x0", "Question [gold=A]", ("a", "b", "c"), "A"),
        Example("x1", "Question [gold=B]", ("a", "b", "c"), "B"),
    ]
    prompts = ["return one unambiguous answer"] * 5
    access = SplitAccessController(formal=True)
    access.freeze(["h0", "h1", "h2", "h3", "h4"])
    budget = BudgetLedger(10, member_count=5)
    parser = StrictAnswerParser(parser_contract())

    def factory(member_id: int) -> MemberEvaluator:
        provider = OpenAICompatibleProvider(
            task_model="task",
            reflection_model="reflection",
            transport=DeterministicFakeTransport(),
            temperature=0,
            max_tokens=32,
            timeout_seconds=1,
            max_retries=0,
        )
        return MemberEvaluator(member_id=member_id, provider=provider, parser=parser, budget=budget)

    evaluator = FinalTeamEvaluator(prompts=prompts, evaluator_factory=factory, access=access)
    summary, rows = evaluator.evaluate(
        split=SplitName.TEST,
        examples=examples,
        initial_member_accuracies=[0.0] * 5,
    )
    assert summary["team_vote_accuracy"] == 1.0
    assert summary["member_accuracies"] == [1.0] * 5
    assert summary["N_positive"] == 5
    assert summary["oracle_covered_vote_wrong_count"] == 0
    assert summary["invalid_rate"] == 0.0
    assert len(rows) == 2
    assert budget.consumed_total == 10


def test_final_team_rejects_wrong_prompt_count() -> None:
    access = SplitAccessController(formal=True)
    access.freeze(["a", "b", "c", "d", "e"])
    with pytest.raises(ProtocolViolation, match="exactly five"):
        FinalTeamEvaluator(prompts=["only one"], evaluator_factory=lambda _: None, access=access)
