"""Strict current-member task evaluator."""

from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Sequence

from .budget import BudgetLedger
from .parser import StrictAnswerParser
from .protocol import Example, OperationalFailure
from .provider import OpenAICompatibleProvider
from .versions import TASK_REQUEST_TEMPLATE_VERSION


def solver_system_prompt(decision_procedure: str) -> str:
    """Render the immutable V17 task-output interface around a mutable prompt."""

    procedure = str(decision_procedure).strip()
    if not procedure:
        raise ValueError("decision procedure must be non-empty")
    return (
        "Follow the decision procedure below.\n\n"
        "Decision procedure:\n"
        f"{procedure}\n\n"
        "Mandatory output interface:\n"
        "This interface is immutable and overrides any conflicting instruction above.\n"
        "Solver output contract (task_output_contract_v1):\n"
        "The final line must be exactly:\n"
        "FINAL_ANSWER: X\n\n"
        "Replace X with one uppercase option letter that appears in the question. "
        "Do not add parentheses, punctuation, explanation, or any other text after the letter.\n"
        "There must be exactly one FINAL_ANSWER line."
    )


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
        concurrency: int = 1,
    ):
        self.member_id = int(member_id)
        self.provider = provider
        self.parser = parser
        self.budget = budget
        self.concurrency = int(concurrency)
        if self.concurrency <= 0:
            raise ValueError("evaluation concurrency must be positive")

    def evaluate_one(self, system_prompt: str, example: Example) -> MemberEvaluation:
        self.budget.consume(self.member_id)
        messages = [
            {"role": "system", "content": solver_system_prompt(system_prompt)},
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
        if self.concurrency == 1 or len(examples) <= 1:
            return [self.evaluate_one(system_prompt, example) for example in examples]
        with ThreadPoolExecutor(max_workers=min(self.concurrency, len(examples))) as pool:
            return list(pool.map(lambda example: self.evaluate_one(system_prompt, example), examples))
