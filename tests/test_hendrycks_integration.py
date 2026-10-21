"""GEPA current all-phase scoring and legacy execution boundary."""
from dataclasses import asdict
from pathlib import Path
import pytest
from independent_gepa.math_scoring import CONTRACT_ID,contract_sha256,RetiredMathScorerError
from independent_gepa.single_prompt_math.math_flexible_answer import classify_prediction,prediction_from_persisted
from independent_gepa.single_prompt_math.math_prediction_validity import resolve_predictions
from independent_gepa.single_prompt_math.scoring import score
from independent_gepa.single_prompt_math.math_domain_v2 import score as old_module_alias
from independent_gepa.single_prompt_math.runtime import Runtime
from independent_gepa.single_prompt_math.runner import load_config
from independent_gepa.math_comparison import benchmark
from independent_gepa.protocol import ProtocolViolation
ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('raw,gold,correct',[(r'\boxed{0.5}',r'\frac{1}{2}',True),(r'\boxed{x+x}','2x',False),('Final answer: 2','2',False)])
def test_optimization_validation_test_and_team_winner_use_identical_core(monkeypatch,raw,gold,correct):
    monkeypatch.setattr(benchmark,'matrix',lambda *a:(_ for _ in ()).throw(AssertionError('SYMBOLIC_CORRECTNESS_FORBIDDEN')))
    pred=classify_prediction(raw);p=resolve_predictions((pred,)*(1 if pred.prediction_valid else 4))
    for phase in ('search','test'):
        rt=Runtime.__new__(Runtime);rt.phase=phase
        assert rt.score_prediction(p,gold) is correct
    assert score(p,gold) is correct and old_module_alias(p,gold) is correct
    assert benchmark.correct(asdict(p),gold) is correct

def test_native_selection_budget_and_seed_configuration_is_preserved():
    import yaml
    old=yaml.safe_load((ROOT/'configs/gepa_single_prompt_math_v6.yaml').read_text())
    new=load_config(ROOT)
    changed={k for k in set(old)|set(new) if old.get(k)!=new.get(k)}
    assert changed=={'experiment_id','schema_version','scoring_policy','math_scoring_sha256'}
    assert new['scoring_policy']==CONTRACT_ID and new['math_scoring_sha256']==contract_sha256()

def test_old_frozen_config_and_cached_prediction_rejected_before_execution(tmp_path):
    with pytest.raises(RetiredMathScorerError):Runtime(tmp_path,{'arms':['strict_validation']},{},'old',None)
    assert not list(tmp_path.iterdir())
    pred=asdict(classify_prediction(r'\boxed{2}'));assert prediction_from_persisted(pred)
    pred.pop('math_scoring_contract');pred.pop('math_scoring_sha256')
    with pytest.raises(ProtocolViolation):prediction_from_persisted(pred)

@pytest.mark.parametrize('module',['scoring_v5','scoring_v7'])
def test_retired_scores_and_continuations_fail_closed(module):
    from importlib import import_module
    with pytest.raises(RetiredMathScorerError):import_module('independent_gepa.single_prompt_math.'+module).score(None,'2')
    from independent_gepa.single_prompt_math.continuation import prepare
    with pytest.raises(RetiredMathScorerError,match='RETIRED'):prepare(None,None,None,None,None)

def test_team_vote_retains_original_grouping_but_scores_selected_raw_answer():
    predictions=[benchmark.classify(raw) for raw in (r'\boxed{x+x}',r'\boxed{2x}',r'\boxed{2x}',r'\boxed{3}',r'\boxed{4}')]
    assert benchmark.team_vote(predictions,'2x') is False
    predictions[0],predictions[1]=predictions[1],predictions[0]
    assert benchmark.team_vote(predictions,'2x') is True

def test_complete_box_on_length_finish_is_not_rejected_by_an_extra_gate():
    p=classify_prediction(r'\boxed{2}','length')
    assert p.prediction_valid and score(resolve_predictions((p,)),'2')
def test_historical_replay_entry_imports_and_fails_closed_without_a_judge(tmp_path):
    from independent_gepa.single_prompt_math.replay_scores import replay
    with pytest.raises(RuntimeError,match='HISTORICAL_MATH_SCORER_RETIRED'):
        replay(tmp_path,None,None,None,tmp_path/'not_created')
    assert not (tmp_path/'not_created').exists()
