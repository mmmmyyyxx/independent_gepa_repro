"""Strict current-member task evaluator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .budget import BudgetLedger
from .parser import StrictAnswerParser
from .protocol import Example, OperationalFailure
from .provider import OpenAICompatibleProvider


@dataclass(frozen=True)
class MemberEvaluation:
    example_id: str
    raw_response: str
    parsed_option: str | None
    valid: bool
    correct: bool
    failure_type: str | None
    finish_reason: str | None
    prompt_tokens: int
    completion_tokens: int
    cache_hit: bool
    operational_status: str = "ok"

    @property
    def score(self) -> float:
        return 1.0 if self.valid and self.correct else 0.0

    def output_record(self) -> dict[str, Any]:
        return {
            "example_id": self.example_id,
            "raw_response": self.raw_response,
            "parsed_option": self.parsed_option,
            "valid": self.valid,
            "correct": self.correct,
            "failure_type": self.failure_type,
            "finish_reason": self.finish_reason,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cache_hit": self.cache_hit,
            "operational_status": self.operational_status,
        }


class MemberEvaluator:
    """Evaluates only one member; it has no team or peer inputs."""

    def __init__(
        self,
        *,
        member_id: int,
        provider: OpenAICompatibleProvider,
        parser: StrictAnswerParser,
        budget: BudgetLedger,
    ):
        self.member_id = int(member_id)
        self.provider = provider
        self.parser = parser
        self.budget = budget

    def evaluate_one(self, system_prompt: str, example: Example) -> MemberEvaluation:
        self.budget.consume(self.member_id)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": example.task_input()},
        ]
        try:
            response, cache_hit = self.provider.complete("task", messages)
        except OperationalFailure:
            raise
        parsed = self.parser.parse(
            response.text,
            option_labels=example.resolved_option_labels,
            gold_answer=example.gold_answer,
            finish_reason=response.finish_reason,
        )
        correct = bool(parsed.correct)
        return MemberEvaluation(
            example_id=example.example_id,
            raw_response=response.text,
            parsed_option=parsed.parsed_option,
            valid=parsed.valid,
            correct=correct,
            failure_type=parsed.failure_type,
            finish_reason=response.finish_reason,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            cache_hit=cache_hit,
        )

    def evaluate(self, system_prompt: str, examples: Sequence[Example]) -> list[MemberEvaluation]:
        if not self.budget.can_consume(self.member_id, len(examples)):
            from .protocol import BudgetExceeded

            raise BudgetExceeded(
                f"member {self.member_id} cannot atomically evaluate batch of {len(examples)}; "
                f"remaining={self.budget.remaining(self.member_id)}"
            )
        return [self.evaluate_one(system_prompt, example) for example in examples]
