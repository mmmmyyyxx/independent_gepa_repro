"""Explicit author-artifact protocol, separate from historical comparison arms."""
from __future__ import annotations

from dataclasses import asdict, dataclass

IDENTITY = "gepa_paper_five_tasks_openlux_qwen37_alias_windows_v3"
CONFIG_PATH = "configs/" + IDENTITY + ".json"
PROTOCOL_PATH = "experiments/protocols/" + IDENTITY
ARTIFACT_COMMIT = "cbefbc1aa0f43dd39874ec4bf42211365dbda42e"
DSPY_COMMIT = "62dc3b634d7dc0c4889abcf905cb4c391ea6b396"
LIVEBENCH_REVISION = "bb66571c8ccf32d3df9e6f48b920d3770ff4aacb"


@dataclass(frozen=True)
class Task:
    key: str
    package: str
    benchmark: str
    program: str
    sizes: tuple[int, int, int]
    budget: int
    metric: str
    predictors: int


TASKS = (
    Task("hotpotqa", "hotpotQA", "HotpotQABench", "HotpotMultiHop", (150, 300, 300),
         6871, "dspy_answer_exact_match", 4),
    Task("ifbench", "IFBench", "IFBench", "IFBenchCoT2StageProgram", (150, 300, 294),
         3593, "author_loose_fraction_of_constraints", 2),
    Task("hover", "hover", "hoverBench", "HoverMultiHop", (150, 300, 300),
         7051, "all_gold_titles_retrieved", 4),
    Task("aime2025", "AIME", "AIMEBench", "CoT", (45, 45, 150),
         1839, "author_integer_answer_field", 1),
    Task("livebench_math", "livebench_math", "LiveBenchMathBench", "CoT", (121, 121, 126),
         1839, "author_livebench_task_dispatch", 1),
)


def draft() -> dict:
    """No source/config preparation can confer a real API grant."""
    return {
        "schema_version": IDENTITY, "status": "PREPARATION_ONLY", "READY_TO_RUN": False,
        "real_api_allowed": False, "authorization": None,
        "paper": "https://arxiv.org/html/2507.19457v2",
        "upstream": {
            "artifact_repository": "https://github.com/gepa-ai/gepa-artifact",
            "artifact_commit": ARTIFACT_COMMIT,
            "dspy_repository": "https://github.com/gepa-ai/dspy",
            "dspy_ref": "gepa_study", "dspy_commit": DSPY_COMMIT,
            "execution_engine": "gepa_artifact.gepa.gepa.GEPA",
            "existing_vendor_gepa": "unchanged; not the paper execution engine",
        },
        "seeds": [0], "repeats": 1,
        "models": {
            "provider_profile": "openlux",
            "solver": "openai/gpt-4.1-mini",
            "reflection": "openai/qwen3.7-flash",
            "reflection_provider_profile": "lwj",
            "reflection_api_key_env": "LWJ_DASHSCOPE_API_KEY",
            "reflection_base_url_env": "LWJ_DASHSCOPE_BASE_URL",
            "api_key_env": "OPENLUX_API_KEY", "base_url_env": "OPENLUX_BASE_URL",
            "temperature": 1.0, "max_tokens": 16384,
            "availability_verified": False, "model_fallback": False,
            "provider_deviation": "OpenLux replaces the paper's direct OpenAI deployment; backend equivalence unverified",
            "optimizer_deviation": "user-requested Qwen3.7-Flash replaces the author task-LM reflection default; alias backend/snapshot unverified",
            "role_binding": "all original program predictors explicitly use solver LM; global DSPy LM is reflection LM; native teacher_lm remains None",
        },
        "optimizer": {
            "run_linearized_gepa": False, "use_merge": False,
            "set_for_merge_minibatch": "val", "track_scores_on": "val",
            "num_dspy_examples_per_gepa_step": 3, "skip_perfect_score": True,
            "teacher_lm": None, "knowledgebase_qe": None,
            "num_iters": None, "max_evals_per_trainval_instance": None,
            "num_threads": None,
            "threading_note": "native GEPA resolves None with os.cpu_count(); author launch script requests final-eval threads=32",
        },
        "tasks": [asdict(t) for t in TASKS],
        "budget": {
            "unit": "native_task_example_metric_evaluations",
            "sum_search_thresholds": sum(t.budget for t in TASKS),
            "native_boundary": "check before iteration; may cross threshold during an indivisible iteration",
            "counter_caveat": "author total_num_evals does not advance on all-perfect/failed-proposal skips; meter actual metric calls separately",
            "iteration_cap": None, "token_ceiling": None, "report_tokens_not_cost": True,
            "baseline_and_final_test": "separate from search accounting",
        },
        "data_policy": {
            "train": "reflection and minibatch comparison",
            "validation": "author native instance Pareto and final best aggregate selection",
            "test": "no search/selection; only after final program is frozen",
            "aime_test": "30 unique questions times 5, original DSPy request caching retained; not 150 unique questions or guaranteed independent draws",
            "livebench_revision": LIVEBENCH_REVISION,
            "hover_train_validation_content_overlap": "one identical claim in author split; user explicitly chose preserve and disclose; never silently resplit",
        },
        "scoring_boundary": {
            "authority": "pinned author per-benchmark code",
            "existing_math_scoring": "unchanged; not imported by this protocol",
            "historical_results": "read-only; not overwritten or relabeled",
        },
        "windows_amendment": {
            "authorized_by_user": True,
            "allowed": "spawn-safe transport for author's AMPS timeout helper only; unchanged scoring functions",
            "required": "source parity, result+feedback differential tests, real timeout/crash/reaping tests",
        },
        "operational_adapter": {
            "identity": "paper_author_engine_metered_transport_v1",
            "transient_retries": 8, "request_timeout_seconds": 120,
            "backoff_seconds": "min(60, 2**attempt)",
            "nontransient_failure": "OperationalHalt; never scored as wrong or swallowed by native except Exception",
            "actual_task_example_attempts": "reserve at root program entry, including aborted attempts; native stopping counter unchanged",
            "ceilings": "finite logical/physical/wall safety limits required in exact per-phase authorization; hitting one aborts, not completes",
            "unknown_failed_attempt_tokens": "reported as unknown, never invented as zero usage",
            "no_semantic_output_retries": True,
            "scope": "source/config/data/environment/provider bound, single-use phase grant, original DSPy request cache scoped per task",
        },
    }
