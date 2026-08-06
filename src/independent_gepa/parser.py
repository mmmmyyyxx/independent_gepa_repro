"""Strict option-letter parser driven by the frozen source-parser contract."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .protocol import ProtocolViolation
from .versions import PARSER_CONTRACT_VERSION


@dataclass(frozen=True)
class ParseResult:
    parsed_option: str | None
    valid: bool
    correct: bool | None
    failure_type: str


class StrictAnswerParser:
    """Reproduce ``task_parser_v1`` without importing the source repository."""

    REQUIRED_FAILURE_TYPES = {
        "valid": "valid",
        "missing_final_answer": "missing_final_answer",
        "multiple_final_answers": "multiple_final_answers",
        "unparseable_final_answer": "unparseable_final_answer",
        "out_of_domain_answer": "out_of_domain_answer",
    }

    def __init__(self, contract: Mapping[str, Any]):
        self.contract = dict(contract)
        if contract.get("schema_version") != PARSER_CONTRACT_VERSION:
            raise ProtocolViolation("unsupported parser contract schema")
        if contract.get("source_parser_version") != "task_parser_v1":
            raise ProtocolViolation("parser contract must identify task_parser_v1")
        if contract.get("answer_format") != "option_letter":
            raise ProtocolViolation("parser contract must use option_letter answers")
        if contract.get("parsed_option_normalization") != "uppercase_option_label":
            raise ProtocolViolation("parser contract must freeze uppercase option-label normalization")
        if contract.get("truncation_policy") != "source_parser_ignores_finish_reason":
            raise ProtocolViolation("parser truncation policy does not match the source parser")
        raw_failures = contract.get("failure_types")
        if raw_failures != self.REQUIRED_FAILURE_TYPES:
            raise ProtocolViolation("parser failure types do not exactly match task_parser_v1")
        line = contract.get("final_answer_line")
        if not isinstance(line, Mapping) or not isinstance(line.get("regex"), str):
            raise ProtocolViolation("parser contract requires a final_answer_line regex")
        flags = 0
        raw_flags = line.get("flags")
        if raw_flags != ["IGNORECASE", "MULTILINE"]:
            raise ProtocolViolation("parser regex flags must exactly match task_parser_v1")
        flags |= re.IGNORECASE | re.MULTILINE
        try:
            self.final_answer_line = re.compile(str(line["regex"]), flags)
        except re.error as exc:
            raise ProtocolViolation(f"invalid parser regex: {exc}") from exc
        if self.final_answer_line.pattern != r"^\s*FINAL_ANSWER\s*:\s*(.*?)\s*$":
            raise ProtocolViolation("parser regex does not exactly match task_parser_v1")

    @staticmethod
    def _labels(option_labels: Sequence[str]) -> tuple[str, ...]:
        if isinstance(option_labels, (str, bytes)) or not option_labels:
            raise ProtocolViolation("parser requires per-example option_labels")
        labels = tuple(str(item).strip().upper() for item in option_labels)
        expected = tuple(chr(ord("A") + index) for index in range(len(labels)))
        if labels != expected:
            raise ProtocolViolation("option_labels must be contiguous uppercase letters")
        return labels

    @staticmethod
    def _result(
        parsed_option: str | None,
        valid: bool,
        failure_type: str,
        gold_answer: str | None,
    ) -> ParseResult:
        correct = None
        if gold_answer is not None:
            correct = bool(valid and parsed_option == str(gold_answer).strip().upper())
        return ParseResult(parsed_option, valid, correct, failure_type)

    def parse(
        self,
        text: str | None,
        *,
        option_labels: Sequence[str],
        gold_answer: str | None = None,
        finish_reason: str | None = None,
    ) -> ParseResult:
        del finish_reason  # The frozen source parser classifies response text only.
        labels = self._labels(option_labels)
        raw = str(text or "")
        matches = self.final_answer_line.findall(raw)
        if not matches:
            return self._result(None, False, "missing_final_answer", gold_answer)
        if len(matches) != 1:
            return self._result(None, False, "multiple_final_answers", gold_answer)
        raw_payload = str(matches[0]).strip()
        if not raw_payload:
            return self._result(None, False, "unparseable_final_answer", gold_answer)
        payload_match = re.fullmatch(
            r"(?:\(\s*)?([A-Z])(?:\s*\))?",
            raw_payload,
            flags=re.IGNORECASE,
        )
        if payload_match is None:
            return self._result(None, False, "out_of_domain_answer", gold_answer)
        answer = payload_match.group(1).upper()
        if answer not in labels:
            return self._result(None, False, "out_of_domain_answer", gold_answer)
        return self._result(answer, True, "valid", gold_answer)

    def assert_golden_parity(self) -> None:
        fixtures = self.contract.get("golden_fixtures")
        if not isinstance(fixtures, list) or not fixtures:
            raise ProtocolViolation("parser contract must include golden_fixtures")
        for index, fixture in enumerate(fixtures):
            if not isinstance(fixture, dict) or not isinstance(fixture.get("expected"), dict):
                raise ProtocolViolation(f"invalid parser fixture at index {index}")
            actual = self.parse(
                fixture.get("text"),
                option_labels=fixture.get("option_labels", ()),
                gold_answer=fixture.get("gold_answer"),
                finish_reason=fixture.get("finish_reason"),
            )
            expected = fixture["expected"]
            expected_tuple = (
                expected.get("parsed_option"),
                bool(expected.get("valid")),
                expected.get("correct"),
                expected.get("failure_type"),
            )
            actual_tuple = (
                actual.parsed_option,
                actual.valid,
                actual.correct,
                actual.failure_type,
            )
            if actual_tuple != expected_tuple:
                raise ProtocolViolation(
                    f"parser parity failure for fixture {fixture.get('name', index)!r}: "
                    f"expected={expected_tuple}, actual={actual_tuple}"
                )
