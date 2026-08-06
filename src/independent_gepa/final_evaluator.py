"""Frozen five-prompt plurality evaluation and aligned aggregate metrics."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from statistics import mean
from typing import Any, Callable, Mapping, Sequence

from .evaluator import MemberEvaluation, MemberEvaluator
from .protocol import Example, ProtocolViolation, SplitAccessController, SplitName


@dataclass(frozen=True)
class VoteDiagnostic:
    example_id: str
    gold_answer: str
    member_answers: tuple[str | None, ...]
    member_correct: tuple[bool, ...]
    vote_answer: str | None
    vote_correct: bool
    tie: bool
    gold_vote_count: int
    highest_wrong_count: int
    vote_margin: int


def plurality(answers: Sequence[str | None]) -> tuple[str | None, bool]:
    counts = Counter(answer for answer in answers if answer is not None)
    if not counts:
        return None, True
    highest = max(counts.values())
    winners = [answer for answer, count in counts.items() if count == highest]
    if len(winners) != 1:
        return None, True
    return winners[0], False


def _binary_correlation(left: Sequence[bool], right: Sequence[bool]) -> float:
    x = [1.0 if item else 0.0 for item in left]
    y = [1.0 if item else 0.0 for item in right]
    mx, my = mean(x), mean(y)
    numerator = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True))
    denominator = math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
    return 0.0 if denominator == 0 else numerator / denominator


EvaluatorFactory = Callable[[int], MemberEvaluator]


class FinalTeamEvaluator:
    def __init__(
        self,
        *,
        prompts: Sequence[str],
        evaluator_factory: EvaluatorFactory,
        access: SplitAccessController,
    ):
        if len(prompts) != 5 or any(not prompt for prompt in prompts):
            raise ProtocolViolation("final evaluator requires exactly five frozen prompts")
        if access.frozen_prompt_hashes is None:
            raise ProtocolViolation("access controller must already contain the frozen team")
        self.prompts = tuple(prompts)
        self.evaluator_factory = evaluator_factory
        self.access = access

    def evaluate(
        self,
        *,
        split: SplitName,
        examples: Sequence[Example],
        initial_member_accuracies: Sequence[float],
    ) -> tuple[dict[str, Any], tuple[VoteDiagnostic, ...]]:
        if len(initial_member_accuracies) != 5:
            raise ProtocolViolation("five frozen initialization accuracies are required for gains and N+")
        self.access.access_for_final_evaluation(split)
        by_member: list[list[MemberEvaluation]] = []
        evaluator_ids: set[int] = set()
        for member_id, prompt in enumerate(self.prompts):
            evaluator = self.evaluator_factory(member_id)
            if id(evaluator) in evaluator_ids:
                raise ProtocolViolation("final evaluators must remain member-isolated")
            evaluator_ids.add(id(evaluator))
            by_member.append(evaluator.evaluate(prompt, examples))
        diagnostics: list[VoteDiagnostic] = []
        for index, example in enumerate(examples):
            rows = [by_member[member_id][index] for member_id in range(5)]
            answers = tuple(row.parsed_option if row.valid else None for row in rows)
            vote_answer, tie = plurality(answers)
            gold_count = sum(answer == example.gold_answer for answer in answers)
            wrong_counts = Counter(
                answer for answer in answers if answer is not None and answer != example.gold_answer
            )
            highest_wrong = max(wrong_counts.values(), default=0)
            diagnostics.append(
                VoteDiagnostic(
                    example_id=example.example_id,
                    gold_answer=example.gold_answer,
                    member_answers=answers,
                    member_correct=tuple(row.correct for row in rows),
                    vote_answer=vote_answer,
                    vote_correct=bool(vote_answer == example.gold_answer),
                    tie=tie,
                    gold_vote_count=gold_count,
                    highest_wrong_count=highest_wrong,
                    vote_margin=gold_count - highest_wrong,
                )
            )
        size = len(examples)
        if size == 0:
            raise ProtocolViolation("final evaluation split must not be empty")
        member_accuracies = [
            sum(row.correct for row in member_rows) / size for member_rows in by_member
        ]
        gains = [
            accuracy - float(initial_member_accuracies[index])
            for index, accuracy in enumerate(member_accuracies)
        ]
        oracle = [any(row.member_correct) for row in diagnostics]
        vote_correct = [row.vote_correct for row in diagnostics]
        oracle_vote_wrong = [covered and not voted for covered, voted in zip(oracle, vote_correct, strict=True)]
        correctness_vectors = [
            [diagnostic.member_correct[member_id] for diagnostic in diagnostics]
            for member_id in range(5)
        ]
        correlations = [
            _binary_correlation(correctness_vectors[left], correctness_vectors[right])
            for left, right in combinations(range(5), 2)
        ]
        same_wrong_pairs = 0
        both_wrong_pairs = 0
        for diagnostic in diagnostics:
            for left, right in combinations(range(5), 2):
                if not diagnostic.member_correct[left] and not diagnostic.member_correct[right]:
                    both_wrong_pairs += 1
                    left_answer = diagnostic.member_answers[left]
                    right_answer = diagnostic.member_answers[right]
                    if left_answer is not None and left_answer == right_answer:
                        same_wrong_pairs += 1
        invalid_count = sum(not row.valid for member_rows in by_member for row in member_rows)
        summary = {
            "artifact_schema_version": "independent_gepa_final_metrics_v1",
            "split": split.value,
            "example_count": size,
            "team_vote_accuracy": sum(vote_correct) / size,
            "member_accuracies": member_accuracies,
            "mean_member_accuracy": mean(member_accuracies),
            "minimum_member_accuracy": min(member_accuracies),
            "oracle_coverage": sum(oracle) / size,
            "oracle_covered_vote_wrong_count": sum(oracle_vote_wrong),
            "oracle_covered_vote_wrong_rate": sum(oracle_vote_wrong) / size,
            "member_gains": gains,
            "N_positive": sum(gain > 0 for gain in gains),
            "invalid_rate": invalid_count / (size * 5),
            "tie_count": sum(row.tie for row in diagnostics),
            "tie_rate": sum(row.tie for row in diagnostics) / size,
            "mean_G": mean(row.gold_vote_count for row in diagnostics),
            "mean_H": mean(row.highest_wrong_count for row in diagnostics),
            "mean_vote_margin": mean(row.vote_margin for row in diagnostics),
            "mean_pairwise_correctness_correlation": mean(correlations),
            "same_wrong_agreement_rate": (
                same_wrong_pairs / both_wrong_pairs if both_wrong_pairs else 0.0
            ),
            "high_order_team_wrong_rate": (
                sum(sum(not item for item in row.member_correct) >= 4 for row in diagnostics) / size
            ),
        }
        return summary, tuple(diagnostics)


def initial_accuracies_from_bundle(
    manifest: Mapping[str, Any], split: SplitName
) -> tuple[float, ...]:
    reference = manifest.get("reference_results")
    if not isinstance(reference, Mapping):
        raise ProtocolViolation("bundle lacks reference_results")
    rows = reference.get("initial_member_accuracies")
    if not isinstance(rows, Mapping):
        raise ProtocolViolation("bundle lacks frozen initial_member_accuracies")
    values = rows.get(split.value)
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) or len(values) != 5:
        raise ProtocolViolation(f"bundle lacks five initialization accuracies for {split.value}")
    return tuple(float(value) for value in values)
