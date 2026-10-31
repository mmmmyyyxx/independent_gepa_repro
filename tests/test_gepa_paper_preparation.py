from __future__ import annotations

import ast
import json
import multiprocessing
from pathlib import Path

import pytest

from independent_gepa.paper_suite.contract import draft, TASKS, CONFIG_PATH
from independent_gepa.paper_suite.data import item_identity
from independent_gepa.paper_suite.sources import author_budgets
from independent_gepa.paper_suite.windows import run_with_timeout
from independent_gepa.paper_suite.control import OperationalHalt


def test_new_paper_protocol_has_no_inherited_team_or_api_authorization():
    plan = draft()
    assert plan["seeds"] == [0] and plan["repeats"] == 1
    assert not plan["READY_TO_RUN"] and not plan["real_api_allowed"]
    assert plan["authorization"] is None
    assert not plan["optimizer"]["use_merge"]
    assert not plan["optimizer"]["run_linearized_gepa"]
    assert plan["optimizer"]["teacher_lm"] is None
    assert plan["models"]["temperature"] == 1.0
    assert plan["budget"]["sum_search_thresholds"] == 21193


def test_aime_repeat_identity_does_not_pretend_duplicate_questions_are_independent():
    a = {"problem": "Synthetic problem", "answer": "1"}
    assert item_identity("aime2025", a) == item_identity("aime2025", dict(a))
    assert next(t for t in TASKS if t.key == "aime2025").sizes == (45, 45, 150)
    assert "not 150 unique" in draft()["data_policy"]["aime_test"]


def test_budget_reader_uses_author_function_not_launching_experiments(tmp_path):
    (tmp_path / "scripts").mkdir()
    path = tmp_path / "scripts/experiment_configs.py"
    path.write_text("raise AssertionError('module import forbidden')\n"
                    "def get_max_invocations(bench, prog, model, opt):\n"
                    "    return len(bench)\n")
    assert author_budgets(tmp_path) == {t.key: len(t.benchmark) for t in TASKS}


@pytest.fixture
def worker_sources(tmp_path):
    base = tmp_path / "gepa_artifact/benchmarks/livebench_math/livebenchmath_utils"
    for group in ("AMPS_Hard", "math_competitions", "olympiad"):
        (base / group).mkdir(parents=True)
        (base / group / "utils.py").write_text("")
    (base / "metric.py").write_text("")
    (base / "util.py").write_text("")
    (base / "AMPS_Hard/utils.py").write_text(
        "import os,time\n"
        "def is_equiv(left,right):\n"
        "    if left=='stall':time.sleep(60)\n"
        "    if left=='crash':os._exit(7)\n"
        "    if left=='bad':raise ValueError('synthetic parse failure')\n"
        "    if left=='large':return 'x'*2000000\n"
        "    return left==right\n")
    return tmp_path


def test_spawn_worker_preserves_value_and_exception(worker_sources):
    assert run_with_timeout(worker_sources, "is_equiv", ("2", "2")) is True
    assert run_with_timeout(worker_sources, "is_equiv", ("2", "3")) is False
    with pytest.raises(ValueError, match="synthetic parse failure"):
        run_with_timeout(worker_sources, "is_equiv", ("bad", "3"))


def test_spawn_timeout_crash_reaping_and_next_request(worker_sources):
    before = {p.pid for p in multiprocessing.active_children()}
    with pytest.raises(TimeoutError):
        run_with_timeout(worker_sources, "is_equiv", ("stall", "0"), timeout=0.1)
    with pytest.raises(OperationalHalt, match="EOF|EXITED_WITHOUT_RESULT"):
        run_with_timeout(worker_sources, "is_equiv", ("crash", "0"))
    assert run_with_timeout(worker_sources, "is_equiv", ("1", "1")) is True
    assert {p.pid for p in multiprocessing.active_children()} == before


def test_spawn_large_result_does_not_deadlock_on_join_before_read(worker_sources):
    assert len(run_with_timeout(worker_sources, "is_equiv", ("large", "0"))) == 2000000


def test_spawn_rejects_unapproved_entrypoints_before_process_start(worker_sources):
    with pytest.raises(ValueError, match="ONLY_AUTHOR"):
        run_with_timeout(worker_sources, "other_function", ())


def test_public_draft_matches_current_protocol():
    path = Path(__file__).resolve().parents[1] / CONFIG_PATH
    assert json.loads(path.read_text()) == json.loads(json.dumps(draft()))


def test_preparation_cli_has_no_execute_or_model_client_branch():
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "scripts/prepare_gepa_paper_suite.py").read_text())
    assert not any(isinstance(n, ast.Attribute) and n.attr in {"LM", "OpenAI", "compile"}
                   for n in ast.walk(tree))
