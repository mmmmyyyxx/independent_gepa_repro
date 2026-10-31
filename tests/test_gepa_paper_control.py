from types import SimpleNamespace
import hashlib
import json

import pytest

from independent_gepa.paper_suite.control import Ledger, OperationalHalt, Transport, install_logical_meter
from independent_gepa.paper_suite.contract import draft, IDENTITY, CONFIG_PATH
from independent_gepa.paper_suite.runtime import validate_grant
from independent_gepa.paper_suite.execution import GRANT_SCHEMA


def response():
    return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2),
                           choices=[SimpleNamespace(finish_reason="stop")],
                           model="synthetic", system_fingerprint="synthetic")


def request():
    return {"model": draft()["models"]["solver"], "temperature": 1.0, "max_tokens": 16384,
            "messages": [{"role": "system", "content": "Synthetic"}, {"role": "user", "content": "Synthetic"}]}


def test_transient_transport_retry_reuses_exact_request_and_accounts_attempts(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl", 10, 10)
    seen = []
    def fake(**kwargs):
        seen.append(kwargs)
        if len(seen) < 3:
            raise TimeoutError()
        return response()
    transport = Transport(fake, ledger, sleep=lambda seconds: None)
    assert transport(**request()).model == "synthetic"
    assert seen == [request()] * 3
    assert ledger.physical == 3 and ledger.logical == 0
    assert ledger.unknown_failed_usage == 2
    assert ledger.tokens["solver"] == {"prompt": 3, "completion": 2}


@pytest.mark.parametrize("code,retry", [(401, False), (400, False), (404, False), (429, True), (503, True)])
def test_provider_error_policy_has_no_credential_or_schema_fallback(tmp_path, code, retry):
    ledger = Ledger(tmp_path / "ledger.jsonl", 10, 10)
    class HTTPFailure(Exception):
        status_code = code
    attempts = []
    def fake(**kwargs):
        attempts.append(1)
        raise HTTPFailure()
    with pytest.raises(OperationalHalt):
        Transport(fake, ledger, retries=2, sleep=lambda _: None)(**request())
    assert len(attempts) == (3 if retry else 1)


def test_operational_failure_cannot_be_swallowed_by_author_except_exception(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl", 10, 1)
    ledger.reserve_physical("solver", "synthetic")
    caught_by_upstream = False
    with pytest.raises(OperationalHalt):
        try:
            Transport(lambda **kwargs: response(), ledger)(**request())
        except Exception:
            caught_by_upstream = True
    assert not caught_by_upstream


def test_logical_meter_counts_cache_reuses_and_never_silently_completes_at_safety_limit(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl", 2, 100)
    metric = ledger.metric(lambda *args: 0)
    assert metric("same request") == metric("same request") == 0
    assert ledger.logical == 2 and ledger.physical == 0
    with pytest.raises(OperationalHalt, match="LOGICAL_SAFETY"):
        metric("same request")


def test_missing_provider_usage_halts_instead_of_becoming_a_wrong_answer(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl", 10, 10)
    with pytest.raises(OperationalHalt, match="SCHEMA_OR_USAGE"):
        Transport(lambda **kwargs: SimpleNamespace(choices=[]), ledger)(**request())


def test_reflection_and_solver_tokens_are_separate(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl", 10, 10)
    transport = Transport(lambda **kwargs: response(), ledger)
    transport(**request())
    transport(**{**request(), "messages": [{"role": "user", "content": "Synthetic reflection"}]})
    assert ledger.tokens["reflection"] == ledger.tokens["solver"] == {"prompt": 3, "completion": 2}


def test_legacy_authorization_cannot_construct_a_client_or_consume_a_scope(tmp_path):
    with pytest.raises(ValueError, match="FRESH_EXACT"):
        validate_grant(tmp_path, tmp_path, {"approved": True, "real_api_allowed": True})
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("field,value,match", [
    ("seed", 42, "TASK_SEED"), ("max_physical_attempts", 0, "FINITE_OPERATIONAL"),
    ("max_elapsed_seconds", None, "FINITE_OPERATIONAL"),
    ("solver_model", "other", "MODEL_OR_PROVIDER"), ("phase", "old_test_resume", "PHASE"),
    ("reflection_model", "other", "REFLECTION_MODEL_OR_PROVIDER"),
    ("reflection_provider", "other", "REFLECTION_MODEL_OR_PROVIDER"),
    ("reflection_deployment_base_url_sha256", "other", "REFLECTION_DEPLOYMENT"),
    ("token_ceiling", 10, "NOT_PREREGISTERED"),
])
def test_invalid_frozen_requests_fail_before_git_imports_or_provider_creation(tmp_path, monkeypatch, field, value, match):
    (tmp_path / "configs").mkdir()
    (tmp_path / CONFIG_PATH).write_text(json.dumps(draft()))
    base = "https://synthetic.invalid/v1"
    monkeypatch.setenv("OPENLUX_BASE_URL", base)
    monkeypatch.setenv("LWJ_DASHSCOPE_BASE_URL", base)
    grant = dict(schema=GRANT_SCHEMA, approved_by="user", READY_TO_RUN=True,
                 real_api_allowed=True, phase="search", roles=["solver", "reflection"], task="aime2025", seed=0, repeat=1,
                 solver_model=draft()["models"]["solver"], provider="openlux", scope_id="synthetic",
                 reflection_model=draft()["models"]["reflection"], reflection_provider="lwj",
                 reflection_deployment_base_url_sha256=hashlib.sha256(base.encode()).hexdigest(),
                 cache_namespace="synthetic", deployment_base_url_sha256=hashlib.sha256(base.encode()).hexdigest(),
                 max_logical_evaluations=5000, max_physical_attempts=100, max_elapsed_seconds=1000)
    grant[field] = value
    with pytest.raises(ValueError, match=match):
        validate_grant(tmp_path, tmp_path, grant)


def test_logical_safety_is_reserved_before_program_or_provider_work(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl", 1, 10)
    body_calls = []
    class Program:
        def __call__(self):
            body_calls.append(1)
            return "synthetic"
    restore = install_logical_meter(Program, ledger)
    try:
        assert Program()() == "synthetic"
        with pytest.raises(OperationalHalt):
            Program()()
        assert len(body_calls) == ledger.logical == 1
    finally:
        restore()
    assert Program()() == "synthetic"


def test_nested_same_class_is_one_example_and_exception_restores_depth(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl", 5, 10)
    class Program:
        def __call__(self, nested=False, fail=False):
            if fail:
                raise ValueError("synthetic")
            return Program()(nested=True) if not nested else 1
    restore = install_logical_meter(Program, ledger)
    try:
        assert Program()() == 1 and ledger.logical == 1
        with pytest.raises(ValueError):
            Program()(fail=True)
        assert Program()() == 1 and ledger.logical == 3
    finally:
        restore()


@pytest.mark.parametrize("roles,role,mutation,error", [
    (["solver"], "reflection", {}, "ROLE_NOT_AUTHORIZED"),
    (["solver", "reflection"], "reflection", {"model": "openai/gpt-4.1-mini-2025-04-14"}, "DECODING_DRIFT"),
    (["solver", "reflection"], "solver", {"api_base": "https://wrong.invalid"}, "DEPLOYMENT_DRIFT"),
])
def test_role_guard_rejects_model_deployment_or_phase_drift_before_dispatch(roles, role, mutation, error):
    from independent_gepa.paper_suite.models import physical_guard, role_route
    route = role_route(role)
    environment = {route["key_env"]: "synthetic-key", route["base_env"]: "https://synthetic.invalid/v1"}
    payload = {**request(), "model": route["model"], "api_base": environment[route["base_env"]], **mutation}
    if role == "reflection":
        payload["messages"] = [{"role": "user", "content": "Synthetic reflection"}]
    calls = []
    with pytest.raises(OperationalHalt, match=error):
        physical_guard(lambda **kwargs: calls.append(kwargs), roles, environment, lambda: None)(**payload)
    assert not calls


def test_solver_only_phase_does_not_construct_reflection_client_or_need_its_key():
    from independent_gepa.paper_suite.models import create_role_lms
    configurations = []
    fake = SimpleNamespace(LM=lambda model, **kwargs: SimpleNamespace(model=model, kwargs=kwargs),
                           ChatAdapter=lambda: "synthetic", configure=lambda **kw: configurations.append(kw))
    lms = create_role_lms(fake, ["solver"], {"OPENLUX_API_KEY": "private-synthetic-key",
                                           "OPENLUX_BASE_URL": "https://synthetic.invalid/v1"})
    assert list(lms) == ["solver"] and configurations[0]["lm"] is lms["solver"]
    assert lms["solver"].kwargs["api_key"] == "env:OPENLUX_API_KEY"


def test_two_role_native_lms_bind_reflection_global_without_storing_credentials():
    from independent_gepa.paper_suite.models import create_role_lms
    configurations = []
    fake = SimpleNamespace(LM=lambda model, **kwargs: SimpleNamespace(model=model, kwargs=kwargs),
                           ChatAdapter=lambda: "synthetic", configure=lambda **kw: configurations.append(kw))
    environment = dict(OPENLUX_API_KEY="private-solver-key", OPENLUX_BASE_URL="https://solver.invalid/v1",
                       LWJ_DASHSCOPE_API_KEY="private-reflection-key", LWJ_DASHSCOPE_BASE_URL="https://reflection.invalid/v1")
    lms = create_role_lms(fake, ["solver", "reflection"], environment)
    assert configurations[0]["lm"] is lms["reflection"]
    assert lms["solver"].model == draft()["models"]["solver"]
    assert lms["reflection"].model == "openai/qwen3.7-flash"
    assert all("private-" not in json.dumps(lm.kwargs) for lm in lms.values())


def test_old_paper_v1_scope_cannot_authorize_substituted_optimizer(tmp_path):
    with pytest.raises(ValueError, match="FRESH_EXACT"):
        validate_grant(tmp_path, tmp_path, {"schema": "gepa_paper_five_tasks_openlux_windows_v1_authorization_v1",
                       "approved_by": "user", "READY_TO_RUN": True, "real_api_allowed": True})
