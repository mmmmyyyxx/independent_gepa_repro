"""Exact real-exponent certificates and immutable historical scoring policies."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from sympy import Add, Float, Integer, Pow, Rational, Symbol, sqrt

from independent_gepa.protocol import ProtocolViolation
from independent_gepa.single_prompt_math.certified_bounds_v7 import definitely_separated
from independent_gepa.single_prompt_math.scoring_v7 import load_policy,score
from independent_gepa.single_prompt_math.math_domain_v2 import worker_deadline
from independent_gepa.single_prompt_math import continuation

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def policy():return load_policy(ROOT)


def test_huge_fractional_exponent_uses_exact_lower_bound(policy):
    exponent=Add(Pow(Integer(5),Integer(43),evaluate=False)/3,-Rational(1,7),evaluate=False)
    large=Pow(Integer(2),exponent,evaluate=False)
    assert definitely_separated(64*sqrt(3),large,policy)
    assert definitely_separated(large,64*sqrt(3),policy)


def test_certified_nonzero_width_real_exponent_interval(policy):
    large=Pow(Integer(2),100+sqrt(2),evaluate=False)
    assert definitely_separated(Integer(4),large,policy)


@pytest.mark.parametrize('left,right',[
    (Integer(2),Pow(Integer(4),Rational(1,2),evaluate=False)),
    (sqrt(2),Pow(Integer(2),Rational(1,2),evaluate=False)),
    (Integer(1),Pow(Integer(2),Rational(1,1000),evaluate=False)),
    (Integer(0),Pow(Integer(2),-1000,evaluate=False)),
    (Integer(1),Pow(Rational(1,2),1000,evaluate=False)),
    (Integer(1),Pow(Integer(2),Symbol('x'),evaluate=False)),
    (Integer(1),Pow(Integer(2),Float('1000.5'),evaluate=False)),
])
def test_near_equal_nonpositive_symbolic_float_cases_defer(policy,left,right):
    assert not definitely_separated(left,right,policy)


def test_lower_bound_certificate_soundness_across_real_exponents(policy):
    certified=0
    for base in [Rational(3,2),Integer(2),Integer(3),2+sqrt(2)]:
        for exponent in [Rational(7,3),Rational(43,7),11+sqrt(2),Rational(111,4)]:
            large=Pow(base,exponent,evaluate=False)
            for small in [Integer(-4),Integer(0),sqrt(2),Integer(100)]:
                if definitely_separated(large,small,policy):
                    certified+=1
                    assert float((large-small).evalf(60))>2
    assert certified>20


def test_resource_limits_retain_unknown(policy):
    large=Pow(2,10**30+Rational(1,3),evaluate=False)
    assert not definitely_separated(Integer(1),large,{**policy,'interval_max_nodes':0})
    assert not definitely_separated(Integer(1),large,{**policy,'interval_max_exponent_bits':4})


@pytest.mark.parametrize('answer,reference,expected',[
    (r'2^{5^{43}/3-1/7}',r'64\sqrt{3}',False),
    (r'2^{3/2}',r'2\sqrt{2}',True),
    (r'\sqrt{8}',r'2\sqrt{2}',True),
    ('{1,2}','{2,1}',True),('3','2',False),
])
def test_isolated_process_handles_fractional_power_and_ordinary_grades(policy,answer,reference,expected):
    with worker_deadline(30):
        assert score(SimpleNamespace(prediction_valid=True,answer=answer),reference,policy=policy) is expected


def test_policy_and_version_dispatch_are_closed(policy):
    assert continuation.load_policy(ROOT,'v7')==policy
    assert continuation.policy_version(policy)=='v7'
    with pytest.raises(ProtocolViolation):continuation.scoring_module('unknown')
    with pytest.raises(ProtocolViolation):continuation.policy_version({'identity':'unknown'})
    with pytest.raises(ProtocolViolation):
        score(SimpleNamespace(prediction_valid=True,answer='2'),'2',policy={**policy,'interval_max_nodes':1})


def terminal_event(**changes):
    return {'key':'fixture','arm':'native_pareto','repeat':1,'phase':'test','split':'test','stage':'scoring',
        'category':'MATH_EVALUATOR_UNRESOLVED_COMPUTATION','event_sha256':'a'*64,**changes}


@pytest.mark.parametrize('changes',[{'phase':'search'},{'stage':'extraction'},{'category':'NETWORK'},{'repeat':2}])
def test_terminal_repair_never_admits_other_operational_failures(policy,changes):
    from independent_gepa.single_prompt_math.paid_repair import PaidTerminalRepairs
    repair=PaidTerminalRepairs(policy)
    with pytest.raises(ProtocolViolation,match='UNRESOLVED'):
        repair.terminal(terminal_event(**changes),(1,'test','test'),{('native_pareto','fixture')},{})


def test_terminal_remains_failure_without_explicit_policy_or_resolution(policy):
    from independent_gepa.single_prompt_math.paid_repair import PaidTerminalRepairs
    context=(1,'test','test');logical={('native_pareto','fixture')}
    with pytest.raises(ProtocolViolation,match='UNRESOLVED'):
        PaidTerminalRepairs().terminal(terminal_event(),context,logical,{})
    repair=PaidTerminalRepairs(policy);repair.terminal(terminal_event(),context,logical,{})
    with pytest.raises(ProtocolViolation,match='RESAMPLED'):repair.reservation('fixture')
    with pytest.raises(ProtocolViolation,match='UNRESOLVED'):repair.close()


@pytest.mark.parametrize('tamper',['terminal','policy','observation','new_call','paid_answer',None])
def test_terminal_acknowledgment_binds_paid_answer_policy_and_original_event(tmp_path,policy,tamper):
    from independent_gepa.single_prompt_math.paid_repair import PaidTerminalRepairs
    from independent_gepa.single_prompt_math.common import digest,write
    repair=PaidTerminalRepairs(policy)
    repair.terminal(terminal_event(),(1,'test','test'),{('native_pareto','fixture')},{})
    paid={'key':'fixture','prediction':{'text':'synthetic fixture'}}
    write(tmp_path/'resolved_answers/fixture.json',paid)
    value={**paid,'correct':False,'valid':True,'answer':'synthetic'}
    event={'key':'fixture','terminal_event_sha256':'a'*64,'policy_sha256':digest(policy),
        'observation_sha256':digest(value),'new_model_calls':0}
    if tamper=='terminal':event['terminal_event_sha256']='b'*64
    if tamper=='policy':event['policy_sha256']='b'*64
    if tamper=='observation':event['observation_sha256']='b'*64
    if tamper=='new_call':event['new_model_calls']=1
    if tamper=='paid_answer':
        value['prediction']={'text':'changed fixture'};event['observation_sha256']=digest(value)
    if tamper:
        with pytest.raises(ProtocolViolation):repair.repaired(event,{'fixture':value},tmp_path)
    else:
        repair.repaired(event,{'fixture':value},tmp_path);repair.close()
        assert repair.count==1
        with pytest.raises(ProtocolViolation):repair.repaired(event,{'fixture':value},tmp_path)
