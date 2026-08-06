from __future__ import annotations

import copy

import pytest

from independent_gepa.parser import StrictAnswerParser
from independent_gepa.protocol import ProtocolViolation
from tests.helpers import parser_contract


def test_parser_golden_parity_and_edge_cases() -> None:
    parser = StrictAnswerParser(parser_contract())
    parser.assert_golden_parity()
    assert parser.parse("Final answer: c").parsed_option == "C"
    assert parser.parse("Final answer: A\nFinal answer: A").valid
    assert parser.parse("Final answer: A\nFinal answer: B").failure_type == "conflicting_answers"
    assert parser.parse(None).failure_type == "empty_output"


def test_parser_parity_failure_is_hard_error() -> None:
    contract = copy.deepcopy(parser_contract())
    contract["golden_fixtures"][0]["expected"]["parsed_option"] = "B"
    with pytest.raises(ProtocolViolation, match="parser parity failure"):
        StrictAnswerParser(contract).assert_golden_parity()


def test_parser_contract_rejects_implicit_or_unsupported_behavior() -> None:
    contract = copy.deepcopy(parser_contract())
    contract["conflict_policy"] = "take_last"
    with pytest.raises(ProtocolViolation, match="conflict"):
        StrictAnswerParser(contract)
