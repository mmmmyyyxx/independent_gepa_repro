"""Certificates never turn an unresolved computation into a correctness verdict."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from sympy import Add,Float,Integer,Pow,Rational,sqrt,pi,Symbol

from independent_gepa.protocol import ProtocolViolation
from independent_gepa.single_prompt_math.certified_bounds import definitely_separated
from independent_gepa.single_prompt_math.scoring_v5 import load_policy,recovery_config,score
from independent_gepa.single_prompt_math.recovery import retry_local_worker
from independent_gepa.single_prompt_math.math_domain_v2 import current_worker_deadline,worker_deadline

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def policy():return load_policy(ROOT)


def test_huge_unevaluated_exponent_has_bounded_separation_certificate(policy):
    exponent=Add(Pow(Integer(3),Integer(77),evaluate=False),Integer(-1),evaluate=False)
    prediction=Pow(2+sqrt(2),exponent,evaluate=False)
    assert definitely_separated(128*sqrt(2),prediction,policy)
    assert definitely_separated(prediction,128*sqrt(2),policy)


@pytest.mark.parametrize('left,right',[
    (Rational(1,3),Rational(1,3)),(sqrt(2)**2,Integer(2)),
    (Rational(10000000001,10000000000),Integer(1)),
    (Float('1.0000001'),Float('1.0000002')),
    (Symbol('x'),Integer(0)),(pi,Integer(3)),
    (Pow(2+sqrt(2),10**30,evaluate=False),Pow(2+sqrt(2),10**30,evaluate=False)),
])
def test_equivalent_close_float_symbolic_and_unsupported_defer_to_pinned_verifier(policy,left,right):
    assert not definitely_separated(left,right,policy)


def test_certificate_soundness_on_varied_closed_rationals_and_radicals(policy):
    expressions=[Integer(-20),Rational(-1,3),Integer(0),sqrt(2),3+sqrt(5),Integer(20),Integer(100),Pow(2+sqrt(2),4)]
    certified=0
    for left in expressions:
        for right in expressions:
            if definitely_separated(left,right,policy):
                certified+=1
                assert abs((left-right).evalf(80))>2
    assert certified>10


def test_node_and_arithmetic_limits_return_unknown(policy):
    limited={**policy,'interval_max_nodes':0}
    assert not definitely_separated(Integer(1),Integer(100),limited)
    limited={**policy,'interval_max_arithmetic_bits':4}
    assert not definitely_separated(Integer(1),Integer(100),limited)


@pytest.mark.parametrize('answer,reference,valid,expected',[
    ('2','2',True,True),('3','2',True,False),
    (r'\frac{1}{2}','0.5',True,True),
    (r'\sqrt{8}',r'2\sqrt{2}',True,True),
    ('{1,2}','{2,1}',True,True),
    ('1','2',False,False),
    (r'(2+\sqrt{2})^{3^{77}-1}',r'128\sqrt{2}',True,False),
])
def test_repaired_process_preserves_ordinary_scores_and_handles_huge_power(policy,answer,reference,valid,expected):
    with worker_deadline(30):
        assert score(SimpleNamespace(prediction_valid=valid,answer=answer),reference,policy=policy) is expected


def test_repeated_ceiling_timeouts_are_unresolved_not_wrong_or_infinite(policy):
    from independent_gepa.single_prompt_math.runner import load_config
    config=recovery_config(load_config(ROOT),policy);deadlines=[]
    def timed_out():
        deadlines.append(current_worker_deadline());raise ProtocolViolation('MATH_EVALUATOR_TIMEOUT')
    with pytest.raises(ProtocolViolation,match='MATH_EVALUATOR_UNRESOLVED_COMPUTATION'):
        retry_local_worker(timed_out,config,30,wait=lambda _:None)
    assert deadlines==[30,60,120,120]


def test_resource_retries_remain_unlimited_and_wrong_answer_is_not_retried(policy):
    from independent_gepa.single_prompt_math.runner import load_config
    config=recovery_config(load_config(ROOT),policy);attempts=[]
    def resource_failure():
        attempts.append(True)
        if len(attempts)<9:raise ProtocolViolation('MATH_EVALUATOR_RESOURCE_TEMPORARY')
        return False
    assert retry_local_worker(resource_failure,config,30,wait=lambda _:None) is False
    assert len(attempts)==9
