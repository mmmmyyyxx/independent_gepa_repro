"""Independent pinned-helper oracle and binary scoring boundary tests."""
import ast,json
from pathlib import Path
import pytest
from independent_gepa.math_scoring import (score_math_response,extract_final_answer,normalization,
    InvalidGroundTruthError,MathScoringInputError,CONTRACT_ID,contract_sha256)
from independent_gepa.math_scoring import _hendrycks
FIXTURE=json.loads((Path(__file__).resolve().parents[0]/'fixtures/hendrycks_oracle.json').read_text())

@pytest.mark.parametrize('row',FIXTURE['normalization'])
def test_independent_normalization_oracle(row):
    if row['error']:
        with pytest.raises(Exception) as error:normalization(row['value'])
        assert type(error.value).__name__==row['error']
    else:assert normalization(row['value'])==row['normalized']

@pytest.mark.parametrize('row',FIXTURE['extraction'])
def test_independent_extraction_oracle(row):
    assert extract_final_answer(row['raw'])==row['extracted']

def test_vendored_helper_asts_equal_original_source():
    tree=ast.parse(Path(_hendrycks.__file__).read_text())
    actual={n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,ast.FunctionDef)}
    assert actual=={name:ast.dump(ast.parse(source).body[0],include_attributes=False) for name,source in FIXTURE['helper_source'].items()}

@pytest.mark.parametrize('pred,gold,expected',[
    (r'\boxed{2}','2',True),(r'\boxed{\frac12}',r'\frac{1}{2}',True),
    (r'\boxed{0.5}',r'\frac{1}{2}',True),(r'\boxed{\sqrt3}',r'\sqrt{3}',True),
    (r'\boxed{x+x}','2x',False),(r'\boxed{\frac{2}{4}}',r'\frac{1}{2}',False),
    (r'\boxed{02}','2',False),('The answer is 2','2',False),
    (r'\boxed{3}','2',False),(r'\boxed{x=2}','2',True),
    (r'\boxed{0.25}',r'\frac{1}{4}',False),(r'\boxed{\sqrt{4}}','2',False),
    (r'\boxed{3} then \boxed{2}','3',False),('', '2',False),
    (None,'2',False),(r'\fbox{2}','2',False)])
def test_scientific_contract(pred,gold,expected):
    r=score_math_response(pred,gold)
    assert r.correct is expected and r.score==int(expected)
    assert r.scoring_contract==CONTRACT_ID and r.contract_sha256==contract_sha256()
    assert type(r.correct) is bool

@pytest.mark.parametrize('gold',[None,'',' ',[],r'\boxed{',r'\fbox{2}',r'\frac'])
def test_invalid_gold_is_input_error_even_when_prediction_missing(gold):
    with pytest.raises(InvalidGroundTruthError):score_math_response(None,gold)

def test_extraction_failure_and_normalization_exception_reasons():
    assert score_math_response('Final Answer: 2','2').reason=='extraction_failure'
    result=score_math_response(r'\boxed{\sqrt}','2')
    assert result.correct is False and result.reason=='normalization_exception_literal_comparison'

def test_resource_input_failure_is_not_a_model_error():
    with pytest.raises(MathScoringInputError):score_math_response(['2'],'2')
    with pytest.raises(MathScoringInputError):score_math_response('x'*1_048_577,'2')
