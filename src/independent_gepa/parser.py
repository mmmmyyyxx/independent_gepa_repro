"""Strict parser driven entirely by the frozen parser contract."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from .protocol import ProtocolViolation


@dataclass(frozen=True)
class ParseResult:
    parsed_option: str | None
    valid: bool
    failure_type: str | None


class StrictAnswerParser:
    def __init__(self, contract: Mapping[str, Any]):
        self.contract = dict(contract)
        legal = contract.get("legal_options")
        patterns = contract.get("accepted_patterns")
        if not isinstance(legal, list) or not legal or not all(isinstance(item, str) for item in legal):
            raise ProtocolViolation("parser contract legal_options must be a non-empty string list")
        if not isinstance(patterns, list) or not patterns:
            raise ProtocolViolation("parser contract accepted_patterns must be a non-empty list")
        self.legal = frozenset(item.upper() for item in legal)
        self.patterns: list[re.Pattern[str]] = []
        for row in patterns:
            if not isinstance(row, dict) or not isinstance(row.get("regex"), str):
                raise ProtocolViolation("each accepted parser pattern requires a regex")
            flags = 0
            for flag in row.get("flags", []):
                if flag == "IGNORECASE":
                    flags |= re.IGNORECASE
                elif flag == "MULTILINE":
                    flags |= re.MULTILINE
                else:
                    raise ProtocolViolation(f"unsupported regex flag: {flag}")
            try:
                compiled = re.compile(row["regex"], flags)
            except re.error as exc:
                raise ProtocolViolation(f"invalid parser regex: {exc}") from exc
            if "answer" not in compiled.groupindex:
                raise ProtocolViolation("accepted parser regex must define named group 'answer'")
            self.patterns.append(compiled)
        if contract.get("conflict_policy") != "terminal_invalid":
            raise ProtocolViolation("only terminal-invalid conflict handling is supported")
        if contract.get("empty_policy") != "terminal_invalid":
            raise ProtocolViolation("only terminal-invalid empty handling is supported")
        truncation = contract.get("truncation_policy")
        if truncation not in {"terminal_invalid", "parse_if_present"}:
            raise ProtocolViolation("unsupported truncation policy")
        self.truncation_policy = str(truncation)
        reasons = contract.get("truncation_finish_reasons", ["length"])
        if not isinstance(reasons, list):
            raise ProtocolViolation("truncation_finish_reasons must be a list")
        self.truncation_finish_reasons = frozenset(str(item) for item in reasons)

    def parse(self, text: str | None, *, finish_reason: str | None = None) -> ParseResult:
        value = "" if text is None else str(text)
        if not value.strip():
            return ParseResult(None, False, "empty_output")
        if finish_reason in self.truncation_finish_reasons and self.truncation_policy == "terminal_invalid":
            return ParseResult(None, False, "truncated_output")
        answers: list[str] = []
        for pattern in self.patterns:
            for match in pattern.finditer(value):
                candidate = match.group("answer").strip().upper()
                answers.append(candidate)
        if not answers:
            return ParseResult(None, False, "no_accepted_answer")
        legal_answers = [answer for answer in answers if answer in self.legal]
        if len(legal_answers) != len(answers):
            return ParseResult(None, False, "illegal_option")
        unique = set(legal_answers)
        if len(unique) != 1:
            return ParseResult(None, False, "conflicting_answers")
        return ParseResult(next(iter(unique)), True, None)

    def assert_golden_parity(self) -> None:
        fixtures = self.contract.get("golden_fixtures")
        if not isinstance(fixtures, list) or not fixtures:
            raise ProtocolViolation("parser contract must include golden_fixtures")
        for index, fixture in enumerate(fixtures):
            if not isinstance(fixture, dict) or not isinstance(fixture.get("expected"), dict):
                raise ProtocolViolation(f"invalid parser fixture at index {index}")
            actual = self.parse(fixture.get("text"), finish_reason=fixture.get("finish_reason"))
            expected = fixture["expected"]
            expected_tuple = (
                expected.get("parsed_option"),
                bool(expected.get("valid")),
                expected.get("failure_type"),
            )
            actual_tuple = (actual.parsed_option, actual.valid, actual.failure_type)
            if actual_tuple != expected_tuple:
                raise ProtocolViolation(
                    f"parser parity failure for fixture {fixture.get('name', index)!r}: "
                    f"expected={expected_tuple}, actual={actual_tuple}"
                )
