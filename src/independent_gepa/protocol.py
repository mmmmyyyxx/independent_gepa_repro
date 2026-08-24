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
    option_labels: tuple[str, ...] | None = None
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
        expected_labels = tuple(chr(ord("A") + index) for index in range(len(normalized_choices)))
        raw_labels = raw.get("option_labels")
        if raw_labels is None:
            option_labels = expected_labels
        elif not isinstance(raw_labels, Sequence) or isinstance(raw_labels, (str, bytes)):
            raise ProtocolViolation("example option_labels must be a sequence of strings")
        else:
            option_labels = tuple(str(item).strip().upper() for item in raw_labels)
        if option_labels != expected_labels:
            raise ProtocolViolation("example option_labels must be contiguous and match choices")
        gold_answer = str(raw["gold_answer"]).strip().upper()
        if gold_answer not in option_labels:
            raise ProtocolViolation("example gold_answer must be one of its option_labels")
        known = {*required, "option_labels"}
        return Example(
            example_id=str(raw["example_id"]),
            question=str(raw["question"]),
            choices=normalized_choices,
            gold_answer=gold_answer,
            option_labels=option_labels,
            metadata={str(key): value for key, value in raw.items() if key not in known},
        )

    @property
    def resolved_option_labels(self) -> tuple[str, ...]:
        if self.option_labels is not None:
            return self.option_labels
        return tuple(chr(ord("A") + index) for index in range(len(self.choices)))

    def to_mapping(self) -> dict[str, Any]:
        return {
            "example_id": self.example_id,
            "question": self.question,
            "choices": list(self.choices),
            "gold_answer": self.gold_answer,
            "option_labels": list(self.resolved_option_labels),
            **dict(self.metadata),
        }

    def task_input(self) -> str:
        lines = [self.question.strip(), "Options:"]
        for label, choice in zip(self.resolved_option_labels, self.choices, strict=True):
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
