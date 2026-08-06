"""Adapter for the actual GEPA v0.1.1 protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ._vendor import import_vendor_gepa
from .evaluator import MemberEvaluation, MemberEvaluator
from .feedback import assert_feedback_isolation
from .protocol import Example, ProtocolViolation

import_vendor_gepa()
from gepa.core.adapter import EvaluationBatch  # type: ignore[import-not-found]  # noqa: E402


@dataclass(frozen=True)
class MemberTrajectory:
    member_id: int
    example: Example
    evaluation: MemberEvaluation


class IndependentGEPAAdapter:
    """One adapter instance belongs to exactly one member run."""

    propose_new_texts = None

    def __init__(self, member_id: int, evaluator: MemberEvaluator):
        if evaluator.member_id != member_id:
            raise ProtocolViolation("adapter/evaluator member identity mismatch")
        self.member_id = int(member_id)
        self.evaluator = evaluator

    @staticmethod
    def _prompt(candidate: Mapping[str, str]) -> str:
        if set(candidate) != {"system_prompt"} or not isinstance(candidate.get("system_prompt"), str):
            raise ProtocolViolation("candidate must contain exactly one mutable system_prompt")
        return candidate["system_prompt"]

    def evaluate(
        self,
        batch: list[Example],
        candidate: dict[str, str],
        capture_traces: bool = False,
    ) -> EvaluationBatch[MemberTrajectory, dict[str, Any]]:
        prompt = self._prompt(candidate)
        results = self.evaluator.evaluate(prompt, batch)
        outputs = [result.output_record() for result in results]
        trajectories = (
            [
                MemberTrajectory(member_id=self.member_id, example=example, evaluation=result)
                for example, result in zip(batch, results, strict=True)
            ]
            if capture_traces
            else None
        )
        return EvaluationBatch(
            outputs=outputs,
            scores=[result.score for result in results],
            trajectories=trajectories,
            objective_scores=None,
        )

    def make_reflective_dataset(
        self,
        candidate: dict[str, str],
        eval_batch: EvaluationBatch[MemberTrajectory, dict[str, Any]],
        components_to_update: list[str],
    ) -> Mapping[str, Sequence[Mapping[str, Any]]]:
        prompt = self._prompt(candidate)
        if components_to_update != ["system_prompt"]:
            raise ProtocolViolation("only system_prompt may be updated")
        if eval_batch.trajectories is None:
            raise ProtocolViolation("reflection requires current-member trajectories")
        records: list[dict[str, Any]] = []
        for trajectory in eval_batch.trajectories:
            if trajectory.member_id != self.member_id:
                raise ProtocolViolation("cross-member trajectory contamination")
            example = trajectory.example
            result = trajectory.evaluation
            records.append(
                {
                    "Current Prompt": prompt,
                    "Question": example.question,
                    "Choices": list(example.choices),
                    "Current Member Response": result.raw_response,
                    "Parsed Answer": result.parsed_option,
                    "Gold Answer": example.gold_answer,
                    "Correct": result.correct,
                    "Valid": result.valid,
                    "Failure Reason": result.failure_type,
                }
            )
        payload = {"system_prompt": records}
        assert_feedback_isolation(payload)
        return payload
