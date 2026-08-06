"""Core immutable protocol records and access controls."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class ProtocolViolation(RuntimeError):
    """Raised when an action would change or violate the comparison protocol."""


class OperationalFailure(RuntimeError):
    """Provider, transport, or schema failure that must not become score zero."""


class BudgetExceeded(ProtocolViolation):
    """A logical evaluation would exceed a frozen member budget."""


class SplitName(str, Enum):
    OPTIMIZATION = "optimization"
    DEVELOPMENT = "development"
    TEST = "test"


@dataclass(frozen=True)
class Example:
    example_id: str
    question: str
    choices: tuple[str, ...]
    gold_answer: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_mapping(raw: Mapping[str, Any]) -> "Example":
        required = ("example_id", "question", "choices", "gold_answer")
        missing = [key for key in required if key not in raw]
        if missing:
            raise ProtocolViolation(f"example is missing required fields: {missing}")
        choices = raw["choices"]
        if not isinstance(choices, Sequence) or isinstance(choices, (str, bytes)):
            raise ProtocolViolation("example choices must be a sequence of strings")
        normalized_choices = tuple(str(item) for item in choices)
        if not normalized_choices:
            raise ProtocolViolation("example choices must not be empty")
        known = set(required)
        return Example(
            example_id=str(raw["example_id"]),
            question=str(raw["question"]),
            choices=normalized_choices,
            gold_answer=str(raw["gold_answer"]).strip().upper(),
            metadata={str(key): value for key, value in raw.items() if key not in known},
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "example_id": self.example_id,
            "question": self.question,
            "choices": list(self.choices),
            "gold_answer": self.gold_answer,
            **dict(self.metadata),
        }

    def task_input(self) -> str:
        lines = [self.question.strip()]
        for index, choice in enumerate(self.choices):
            label = chr(ord("A") + index)
            lines.append(f"({label}) {choice}")
        return "\n".join(lines)


@dataclass
class SplitAccessController:
    """Enforces optimization/development/test lifecycle rules."""

    formal: bool
    expected_members: int = 5
    frozen_prompt_hashes: tuple[str, ...] | None = None
    accesses: list[str] = field(default_factory=list)
    development_evaluated: bool = False
    test_evaluated: bool = False

    def access_for_optimization(self, split: SplitName) -> None:
        if split is not SplitName.OPTIMIZATION:
            raise ProtocolViolation(f"{split.value} cannot be accessed during optimization")
        self.accesses.append("optimization:optimization")

    def freeze(self, prompt_hashes: Sequence[str]) -> None:
        if self.frozen_prompt_hashes is not None:
            raise ProtocolViolation("final prompts are already frozen")
        hashes = tuple(str(item) for item in prompt_hashes)
        if len(hashes) != self.expected_members or any(not item for item in hashes):
            raise ProtocolViolation(f"exactly {self.expected_members} prompt hashes are required to freeze")
        self.frozen_prompt_hashes = hashes

    def access_for_final_evaluation(self, split: SplitName) -> None:
        if self.frozen_prompt_hashes is None:
            raise ProtocolViolation("final prompts must be frozen before final evaluation")
        if split is SplitName.OPTIMIZATION:
            raise ProtocolViolation("optimization split is not a final-evaluation split")
        if split is SplitName.DEVELOPMENT:
            if self.development_evaluated:
                raise ProtocolViolation("development may be evaluated at most once")
            self.development_evaluated = True
        elif split is SplitName.TEST:
            if not self.formal:
                raise ProtocolViolation("test evaluation is allowed only for a formal run")
            if self.test_evaluated:
                raise ProtocolViolation("test may be evaluated at most once")
            self.test_evaluated = True
        self.accesses.append(f"final:{split.value}")
