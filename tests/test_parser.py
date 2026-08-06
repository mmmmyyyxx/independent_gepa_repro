from __future__ import annotations

import copy

import pytest

from independent_gepa.parser import StrictAnswerParser
from independent_gepa.protocol import ProtocolViolation
from tests.helpers import parser_contract


def test_parser_golden_parity_and_edge_cases() -> None:
    parser = StrictAnswerParser(parser_contract())
    parser.assert_golden_parity()
    labels = ("A", "B", "C")
    assert parser.parse("FINAL_ANSWER: c", option_labels=labels).parsed_option == "C"
    assert not parser.parse(
        "FINAL_ANSWER: A\nFINAL_ANSWER: A", option_labels=labels
    ).valid
    assert (
        parser.parse(
            "FINAL_ANSWER: A\nFINAL_ANSWER: B", option_labels=labels
        ).failure_type
        == "multiple_final_answers"
    )
    assert parser.parse(None, option_labels=labels).failure_type == "missing_final_answer"


def test_parser_parity_failure_is_hard_error() -> None:
    contract = copy.deepcopy(parser_contract())
    contract["golden_fixtures"][0]["expected"]["parsed_option"] = "B"
    with pytest.raises(ProtocolViolation, match="parser parity failure"):
        StrictAnswerParser(contract).assert_golden_parity()


def test_parser_contract_rejects_implicit_or_unsupported_behavior() -> None:
    contract = copy.deepcopy(parser_contract())
    contract["failure_types"]["multiple_final_answers"] = "take_last"
    with pytest.raises(ProtocolViolation, match="failure types"):
        StrictAnswerParser(contract)


def test_parser_uses_per_example_option_range() -> None:
    parser = StrictAnswerParser(parser_contract())
    three = parser.parse("FINAL_ANSWER: D", option_labels=("A", "B", "C"))
    four = parser.parse("FINAL_ANSWER: D", option_labels=("A", "B", "C", "D"))
    assert not three.valid
    assert three.failure_type == "out_of_domain_answer"
    assert four.valid
    assert four.parsed_option == "D"


def test_parser_duplicate_same_and_different_are_both_multiple() -> None:
    parser = StrictAnswerParser(parser_contract())
    labels = ("A", "B", "C")
    same = parser.parse("FINAL_ANSWER: A\nFINAL_ANSWER: A", option_labels=labels)
    different = parser.parse("FINAL_ANSWER: A\nFINAL_ANSWER: B", option_labels=labels)
    assert same.failure_type == "multiple_final_answers"
    assert different.failure_type == "multiple_final_answers"


def test_parser_failure_types_match_task_parser_v1() -> None:
    parser = StrictAnswerParser(parser_contract())
    labels = ("A", "B", "C")
    assert parser.parse("reasoning only", option_labels=labels).failure_type == (
        "missing_final_answer"
    )
    assert parser.parse("FINAL_ANSWER:", option_labels=labels).failure_type == (
        "unparseable_final_answer"
    )
    assert parser.parse("FINAL_ANSWER: Z", option_labels=labels).failure_type == (
        "out_of_domain_answer"
    )


def test_parser_reports_correctness_in_golden_parity_shape() -> None:
    parser = StrictAnswerParser(parser_contract())
    labels = ("A", "B", "C")
    correct = parser.parse(
        "FINAL_ANSWER: B",
        option_labels=labels,
        gold_answer="B",
    )
    wrong = parser.parse(
        "FINAL_ANSWER: B",
        option_labels=labels,
        gold_answer="A",
    )
    assert correct.correct is True
    assert wrong.correct is False
