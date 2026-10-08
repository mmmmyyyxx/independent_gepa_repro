from __future__ import annotations

from pathlib import Path
import pytest

from independent_gepa.math_comparison.candidate_guard import candidate_failures, candidate_valid
from independent_gepa.math_comparison.contract import write,digest
from independent_gepa.math_comparison.evaluation import audit_selected
from independent_gepa.math_comparison.search import MathAdapter, INITIAL
from independent_gepa.math_comparison.runner import require_fresh_user_grant
from independent_gepa.protocol import ProtocolViolation


def example(reference: str) -> list[dict]:
    return [{'example_id':'synthetic', 'problem':'A synthetic arithmetic problem.', 'reference':reference}]


@pytest.mark.parametrize(('prompt','reference'), [
    (r'Keep exact arithmetic. If the gold answer is \frac{23}{80}, return it.', r'\frac{23}{80}'),
    ('A previous result was .2875; prefer that exact result.', r'\frac{23}{80}'),
    (r'Use the exact result \dfrac {23} {80} after simplification.', r'\frac{23}{80}'),
    ('In Example 2 the answer is 9; follow its solution.', '9'),
    ('As seen in sample #4, avoid that failure.', '1'),
    ('For example, compute 8 - 31 = -23 correctly.', '-23'),
    (r'Keep this simplified form 11-6\sqrt{2}.', r'11-6\sqrt{2}'),
    ('Use (x-5)(3x+5) in factorizations.', '(x-5)(3x+5)'),
    ('The answer is 0.', '0'),
])
def test_short_source_copy_is_rejected(prompt, reference):
    assert candidate_failures(prompt, example(reference))


@pytest.mark.parametrize('prompt', [
    INITIAL,
    'Solve with exact arithmetic; verify signs and dimensional consistency.',
    'Use 2 independent checks when feasible. Preserve the immutable output format.',
    'Check ax+b=0 and the sign of the discriminant; do not round early.',
    'Compute the answer from the problem and verify it before returning.',
    'Consider 90 degree angles and 180 degree straight angles when applicable.',
    'Provide internally a complete derivation, then return only the prescribed final line.',
    'Reason internally. Do not show your reasoning.',
    'Always verify the answer by substitution.',
    'Provide a complete derivation internally; return only the prescribed final line.',
    'Show the reasoning silently before emitting the final answer.',
    'Always return 1 line in the prescribed format.',
    'The answer should be verified using 2 independent checks.',
    'For example, use 2 independent checks when feasible.',
    'Distinguish case 1 for positive signs and case 2 for negative signs.',
    'Check critical points unless the solution requires a separate boundary analysis.',
])
def test_generic_reasoning_and_constants_remain_allowed(prompt):
    rows = example('0') + example('1') + example('2') + example(r'\frac{23}{80}')
    assert candidate_valid(prompt, rows)


def test_scalar_match_does_not_match_part_of_other_number():
    assert candidate_valid('For example, compute 13 + 12 = 25 carefully.', example('5'))


@pytest.mark.parametrize('prompt', [
    'Provide the complete derivation leading to the final result.',
    'Present your solution clearly before the final answer.',
    'Internally check the result; show the full derivation in the response.',
    'You must provide a step-by-step logical deduction.',
])
def test_visible_derivation_cannot_replace_immutable_single_line_output(prompt):
    assert 'VISIBLE_REASONING_OUTPUT_CONFLICT' in candidate_failures(prompt, example('1'))


def test_output_contract_cannot_have_an_exception_for_requested_work():
    prompt='Your response has no extra text, other than the solution process if requested.'
    assert 'IMMUTABLE_SINGLE_LINE_EXCEPTION' in candidate_failures(prompt, example('1'))


@pytest.mark.parametrize('prompt', ['Always output 9.', 'Regardless of the problem, return 9.', 'Always return the same answer.'])
def test_fixed_answer_guard_does_not_confuse_verification_with_assignment(prompt):
    assert 'FIXED_ANSWER_INSTRUCTION' in candidate_failures(prompt, example('1'))


def test_rejected_copy_never_dispatches_solver_and_keeps_native_metric_charge(tmp_path):
    class NoSolver:
        def solve(self, *args): raise AssertionError('Rejected source copy reached Solver')
    rows = example(r'\frac{23}{80}')
    adapter = MathAdapter(NoSolver(), rows, 0, 0, tmp_path)
    batch = adapter.evaluate(rows, {'system_prompt':r'Use the answer \frac{23}{80}.'}, True)
    assert batch.scores == [0.0] and adapter.metrics_used == 1 and not adapter.evaluated


def test_entire_frozen_pool_is_checked_before_any_audit_request(tmp_path):
    class NoSolver:
        def solve(self, *args): raise AssertionError('Conformance failure reached paid audit')
    private = tmp_path/'private'
    selections = [{'window':0, 'member':0, 'selected':[{'prompt':'Example 2 has answer 9.'}]}]
    write(private/'SEARCH_COMPLETE.json', {'selection_hash':digest(selections)})
    with pytest.raises(ProtocolViolation, match='FROZEN_CANDIDATE_CONFORMANCE_FAILURE'):
        audit_selected(NoSolver(), tmp_path/'missing_bundle', example('9'), selections, private)


def test_source_repair_cannot_reuse_historical_consumed_user_grant(tmp_path):
    task_sha='a'*64
    write(tmp_path/'runs/old_attempt/frozen_attempt.json', {'user_task_sha256':task_sha, 'identity':'b'*64})
    write(tmp_path/('runs/authorization_consumed/'+'b'*64+'.json'), {})
    with pytest.raises(ProtocolViolation, match='USER_API_GRANT_ALREADY_CONSUMED'):
        require_fresh_user_grant(tmp_path, task_sha)
    require_fresh_user_grant(tmp_path, 'c'*64)


def test_grant_keyed_consumption_does_not_require_run_completion(tmp_path):
    write(tmp_path/('runs/authorization_consumed/user_grant_'+'a'*64+'.json'), {})
    with pytest.raises(ProtocolViolation, match='USER_API_GRANT_ALREADY_CONSUMED'):
        require_fresh_user_grant(tmp_path, 'a'*64)
