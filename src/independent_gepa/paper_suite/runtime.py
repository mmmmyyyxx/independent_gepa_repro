"""Fresh, phase-scoped execution adapter for the pinned author artifact.

Preparation never creates the authorization consumed here. No legacy run/config
or readiness receipt is accepted. Native search/scoring bodies stay upstream.
"""
from __future__ import annotations

import importlib
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from .contract import IDENTITY, TASKS, CONFIG_PATH, PROTOCOL_PATH, draft
from .control import Ledger, OperationalHalt, install_transport, request_role, install_logical_meter
from .data import canonical, decode_metadata, digest
from .sources import audit, file_hash, git
from .windows import install
from .models import create_role_lms, physical_guard, role_route
from .execution import (EXECUTION_BINDINGS, GRANT_SCHEMA, PhaseFutures,
                        execution_binding, load_execution_policy)


MODEL_BINDINGS = ("solver_model", "deployment_base_url_sha256", "reflection_model",
                  "reflection_provider", "reflection_deployment_base_url_sha256")


def within(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("PAPER_SCOPE_PATH_ESCAPE")
    return resolved


def validate_phase_dependencies(workspace: Path, grant: dict) -> None:
    """Enforce the global search/Test barrier even for a direct phase command."""
    required = []
    if grant["phase"] in {"baseline", "final_test"}:
        required.append(("search", "search_receipts"))
    if grant["phase"] == "final_test":
        required.append(("baseline", "baseline_receipts"))
    for phase, field in required:
        bindings = grant.get(field)
        if not isinstance(bindings, dict) or set(bindings) != {t.key for t in TASKS}:
            raise ValueError("COMPLETE_FIVE_TASK_PHASE_BARRIER_REQUIRED:" + phase)
        for task, binding in bindings.items():
            path = within(workspace / binding["path"], workspace)
            if file_hash(path) != binding.get("sha256"):
                raise ValueError("PHASE_DEPENDENCY_RECEIPT_HASH_MISMATCH")
            previous = json.loads(path.read_text(encoding="utf-8"))
            keys = ("source_sha", "config_sha256", "data_receipt_sha256", *MODEL_BINDINGS, *EXECUTION_BINDINGS)
            if (previous.get("status") != "COMPLETE" or previous.get("phase") != phase
                    or previous.get("task") != task or any(previous.get(k) != grant[k] for k in keys)
                    or not previous.get("phase_futures", {}).get("drained")
                    or previous["phase_futures"].get("pending") != 0):
                raise ValueError("PHASE_DEPENDENCY_IDENTITY_OR_DRAIN_MISMATCH")
            if task == grant.get("task") and previous.get("cache_namespace") != grant.get("cache_namespace"):
                raise ValueError("TASK_SEARCH_BASELINE_TEST_CACHE_NAMESPACE_MUST_MATCH")
            if phase == "search":
                if file_hash(path.parent / "selected_program.json") != previous.get("selected_program_sha256"):
                    raise ValueError("ALL_SELECTED_PROGRAMS_MUST_BE_FROZEN_BEFORE_TEST")


def validate_grant(root: Path, workspace: Path, grant: dict) -> dict:
    """Validate before importing DSPy/LiteLLM or constructing any model client."""
    if (grant.get("schema") != GRANT_SCHEMA or grant.get("approved_by") != "user"
            or grant.get("READY_TO_RUN") is not True or grant.get("real_api_allowed") is not True):
        raise ValueError("FRESH_EXACT_PAPER_API_AUTHORIZATION_REQUIRED")
    if grant.get("phase") not in {"canary", "baseline", "search", "final_test"}:
        raise ValueError("PAPER_PHASE_REQUIRED")
    expected_roles = ["solver", "reflection"] if grant["phase"] in {"search", "canary"} else ["solver"]
    if grant.get("roles") != expected_roles:
        raise ValueError("EXACT_PHASE_ROLE_AUTHORIZATION_REQUIRED")
    task = next((t for t in TASKS if t.key == grant.get("task")), None)
    if task is None or grant.get("seed") != 0 or grant.get("repeat") != 1:
        raise ValueError("AUTHOR_TASK_SEED_REPEAT_MISMATCH")
    expected = draft()
    if canonical(json.loads((root / CONFIG_PATH).read_text())) != canonical(expected):
        raise ValueError("UNIMPLEMENTED_PAPER_CONFIGURATION_VARIANT")
    if grant.get("token_ceiling") is not None:
        raise ValueError("TOKEN_CEILING_VARIANT_NOT_PREREGISTERED")
    if grant.get("solver_model") != expected["models"]["solver"] or grant.get("provider") != "openlux":
        raise ValueError("PAPER_MODEL_OR_PROVIDER_MISMATCH")
    if (grant.get("reflection_model") != expected["models"]["reflection"]
            or grant.get("reflection_provider") != expected["models"]["reflection_provider_profile"]):
        raise ValueError("PAPER_REFLECTION_MODEL_OR_PROVIDER_MISMATCH")
    if not grant.get("scope_id") or not str(grant["scope_id"]).replace("_", "").replace("-", "").isalnum():
        raise ValueError("FRESH_SCOPE_ID_REQUIRED")
    namespace = grant.get("cache_namespace", "")
    if not namespace or not namespace.replace("_", "").replace("-", "").isalnum():
        raise ValueError("FRESH_BOUND_CACHE_NAMESPACE_REQUIRED")
    base = os.environ.get("OPENLUX_BASE_URL", "")
    if not base or hashlib.sha256(base.encode()).hexdigest() != grant.get("deployment_base_url_sha256"):
        raise ValueError("EXACT_OPENLUX_DEPLOYMENT_BINDING_REQUIRED")
    reflection_base = os.environ.get(role_route("reflection")["base_env"], "")
    if (not reflection_base or hashlib.sha256(reflection_base.encode()).hexdigest()
            != grant.get("reflection_deployment_base_url_sha256")):
        raise ValueError("EXACT_REFLECTION_DEPLOYMENT_BINDING_REQUIRED")
    for field in ("max_logical_evaluations", "max_physical_attempts", "max_elapsed_seconds"):
        if type(grant.get(field)) is not int or grant[field] <= 0:
            raise ValueError("FINITE_OPERATIONAL_CEILINGS_REQUIRED:" + field)
    if grant["phase"] == "search" and grant["max_logical_evaluations"] < task.budget + task.sizes[1] + 6:
        raise ValueError("SAFETY_CEILING_CANNOT_TRUNCATE_NORMAL_NATIVE_ITERATION")
    if grant["phase"] == "search" and grant.get("native_search_threshold") != task.budget:
        raise ValueError("EXACT_NATIVE_SEARCH_THRESHOLD_REQUIRED")
    expected_execution = execution_binding(root, os.cpu_count())
    if any(grant.get(key) != value for key, value in expected_execution.items()):
        raise ValueError("EXACT_EXECUTION_POLICY_AND_THREADS_REQUIRED")
    if grant.get("source_sha") != git(root, "rev-parse", "HEAD") or git(root, "status", "--porcelain"):
        raise ValueError("CLEAN_COMMITTED_PAPER_SOURCE_REQUIRED")
    if grant.get("config_sha256") != file_hash(root / CONFIG_PATH):
        raise ValueError("PAPER_CONFIGURATION_HASH_MISMATCH")
    if grant.get("environment_lock_sha256") != file_hash(root / "requirements/paper-suite-windows.lock.txt"):
        raise ValueError("PAPER_ENVIRONMENT_LOCK_MISMATCH")
    import importlib.metadata
    environment_inventory = root / PROTOCOL_PATH / "environment_inventory.json"
    versions = json.loads(environment_inventory.read_text())
    for name, version in versions.items():
        try:
            observed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            observed = None
        if observed != version:
            raise ValueError("PAPER_INSTALLED_DEPENDENCY_MISMATCH:" + name)
    nlp_inventory = json.loads((root / PROTOCOL_PATH / "nlp_inventory.json").read_text())
    for relative, sha in nlp_inventory["files"].items():
        if file_hash(within(workspace / "nlp/nltk_data" / relative, workspace / "nlp/nltk_data")) != sha:
            raise ValueError("FROZEN_NLP_RESOURCE_MISMATCH")
    source_observed = audit(workspace / "upstream")
    source_expected = json.loads((root / PROTOCOL_PATH / "source_inventory.json").read_text())
    if canonical(source_observed) != canonical(source_expected):
        raise ValueError("AUDITED_AUTHOR_SOURCE_INVENTORY_MISMATCH")
    bundle = within(workspace / grant["data_bundle"], workspace)
    if file_hash(bundle / "receipt.json") != grant.get("data_receipt_sha256"):
        raise ValueError("PAPER_DATA_RECEIPT_MISMATCH")
    if grant["data_receipt_sha256"] != file_hash(root / PROTOCOL_PATH / "data_inventory.json"):
        raise ValueError("DATA_MUST_MATCH_AUDITED_AUTHOR_MEMBERSHIP")
    receipt = json.loads((bundle / "receipt.json").read_text())
    for split, values in receipt["splits"][task.key].items():
        if file_hash(bundle / task.key / (split + ".jsonl")) != values["file_sha256"]:
            raise ValueError("PAPER_DATA_FILE_HASH_MISMATCH")
    if task.key in {"hover", "hotpotqa"} and grant["phase"] != "canary":
        index = workspace / "retrieval/index_receipt.json"
        if not index.exists() or file_hash(index) != grant.get("retrieval_receipt_sha256"):
            raise ValueError("FINISHED_BM25_INDEX_RECEIPT_REQUIRED")
        index_receipt = json.loads(index.read_text())
        if not index_receipt["index_ready"]:
            raise ValueError("BM25_INDEX_NOT_READY")
        for relative, sha in index_receipt["index_files"].items():
            if file_hash(within(workspace / "retrieval/bm25s_retriever" / relative,
                                workspace / "retrieval/bm25s_retriever")) != sha:
                raise ValueError("BM25_INDEX_FILE_HASH_MISMATCH")
        if file_hash(workspace / "retrieval/wiki.abstracts.2017.jsonl") != index_receipt["corpus_sha256"]:
            raise ValueError("BM25_CORPUS_HASH_MISMATCH")
    if grant["phase"] != "canary":
        canary = within(workspace / grant["canary_receipt"], workspace)
        if file_hash(canary) != grant.get("canary_receipt_sha256"):
            raise ValueError("EXACT_MODEL_CANARY_RECEIPT_REQUIRED")
        previous = json.loads(canary.read_text())
        if (previous.get("phase") != "canary" or previous.get("status") != "COMPLETE"
                or previous.get("source_sha") != grant["source_sha"]
                or previous.get("config_sha256") != grant["config_sha256"]
                  or any(previous.get(key) != grant[key] for key in MODEL_BINDINGS + EXECUTION_BINDINGS)):
            raise ValueError("MODEL_CANARY_SCOPE_MISMATCH")
    if grant["phase"] == "final_test":
        selection = within(workspace / grant["selection_receipt"], workspace)
        if file_hash(selection) != grant.get("selection_receipt_sha256"):
            raise ValueError("SEARCH_SELECTION_RECEIPT_REQUIRED")
        parent = json.loads(selection.read_text())
        if (parent.get("phase") != "search" or parent.get("status") != "COMPLETE"
                or parent.get("task") != task.key or parent.get("source_sha") != grant["source_sha"]
                or parent.get("config_sha256") != grant["config_sha256"]
                or any(parent.get(key) != grant[key] for key in MODEL_BINDINGS + EXECUTION_BINDINGS)
                or parent.get("data_receipt_sha256") != grant["data_receipt_sha256"]
                or parent.get("selected_program_sha256") != grant.get("selected_program_sha256")):
            raise ValueError("SELECTED_PROGRAM_PROVENANCE_MISMATCH")
    validate_phase_dependencies(workspace, grant)
    return {"task": task, "bundle": bundle}


def execute(root: Path, workspace: Path, authorization: Path):
    grant = json.loads(authorization.read_text())
    binding = validate_grant(root, workspace, grant)
    task, phase = binding["task"], grant["phase"]
    # Single-use scope is consumed before provider creation; abandoned startup
    # requires a new grant, not an efficacy-dependent rerun or silent resume.
    consumed = root / "runs/paper_authorization_consumed"
    consumed.mkdir(exist_ok=True)
    with (consumed / (digest(grant) + ".json")).open("xb") as stream:
        stream.write(canonical({"scope_id": grant["scope_id"]}) + b"\n")
    run = workspace / "execution" / grant["scope_id"]
    run.mkdir(parents=True, exist_ok=False)
    deadline = time.monotonic() + grant["max_elapsed_seconds"]
    def check_time():
        if time.monotonic() >= deadline:
            raise OperationalHalt("PHASE_WALL_TIME_SAFETY_LIMIT")
    ledger = Ledger(run / "ledger.jsonl", grant["max_logical_evaluations"], grant["max_physical_attempts"])
    ledger.wall_deadline = deadline
    result = {"scope_id": grant["scope_id"], "phase": phase, "source_sha": grant["source_sha"],
              "cache_namespace": grant["cache_namespace"],
              "task": task.key, "config_sha256": grant["config_sha256"],
              "data_receipt_sha256": grant["data_receipt_sha256"],
              **{key: grant[key] for key in MODEL_BINDINGS + EXECUTION_BINDINGS}, "status": "ABORTED"}
    original = None
    restore_meter = None
    futures = PhaseFutures(ledger)
    try:
        policy = load_execution_policy(root)
        sys.path.insert(0, str(workspace / "upstream/dspy-study"))
        sys.path.insert(0, str(workspace / "upstream/gepa-artifact"))
        cache = workspace / "request_cache" / grant["cache_namespace"]
        cache.mkdir(parents=True, exist_ok=True)
        cache_identity = {k: grant[k] for k in ("source_sha", "config_sha256", "data_receipt_sha256",
                          "environment_lock_sha256", "task", "seed", "repeat", *MODEL_BINDINGS,
                          *EXECUTION_BINDINGS)}
        marker = cache / "identity.json"
        if marker.exists():
            if json.loads(marker.read_text()) != cache_identity:
                raise ValueError("PAPER_CACHE_SCOPE_MISMATCH")
        else:
            with marker.open("xb") as stream:
                stream.write(canonical(cache_identity) + b"\n")
        os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP="True", WANDB_MODE="offline",
                          HF_HUB_OFFLINE="1", HF_DATASETS_OFFLINE="1",
                          DSPY_CACHEDIR=str(cache / "dspy_cache"), NLTK_DATA=str(workspace / "nlp/nltk_data"))
        import dspy
        import litellm
        if not Path(dspy.__file__).resolve().is_relative_to(workspace / "upstream/dspy-study"):
            raise ValueError("AUTHOR_DSPY_IMPORT_MISMATCH")
        import dspy.utils.parallelizer as parallelizer
        futures.install(parallelizer)
        from .offline import verify_nlp
        verify_nlp()
        if litellm.cache is not None:
            raise ValueError("UNMETERED_SECONDARY_LITELLM_CACHE_FORBIDDEN")
        lms = create_role_lms(dspy, grant["roles"], os.environ)
        lm = lms["solver"]
        original = install_transport(litellm, ledger, run / "paid_responses")
        # Resolve credentials only at the physical boundary so no key is saved
        # in DSPy program state, reflection traces or checkpoint serialization.
        litellm.completion = physical_guard(litellm.completion, grant["roles"], os.environ, check_time)
        if phase == "canary":
            first = lm(messages=[{"role": "system", "content": "Reply with one integer."},
                                 {"role": "user", "content": "What is one plus one?"}])
            second = lms["reflection"]("Return a short instruction enclosed in triple backticks.", max_tokens=16384)
            if not first or not second or not all(str(x).strip() for x in first + second):
                raise OperationalHalt("EMPTY_CANARY_RESPONSE")
        else:
            module = importlib.import_module("gepa_artifact.benchmarks." + task.package)
            meta = module.benchmark[0]
            program = meta.program[0].deepcopy()
            program.set_lm(lm)
            restore_meter = install_logical_meter(type(program), ledger)
            if task.key == "livebench_math":
                amp = importlib.import_module("gepa_artifact.benchmarks.livebench_math.livebenchmath_utils.AMPS_Hard.utils")
                install(workspace / "upstream/gepa-artifact", author_module=amp)
            if task.key in {"hover", "hotpotqa"}:
                import bm25s
                import Stemmer
                hover = importlib.import_module("gepa_artifact.benchmarks.hover.hover_program")
                hover.retriever = bm25s.BM25.load(str(workspace / "retrieval/bm25s_retriever"),
                                                 mmap=policy["retrieval_mmap"])
                hover.stemmer = Stemmer.Stemmer("english")
                with (workspace / "retrieval/wiki.abstracts.2017.jsonl").open(encoding="utf-8") as stream:
                    hover.corpus = [f"{x['title']} | {' '.join(x['text'])}" for x in map(json.loads, stream)]
                hover.initialized = True
            input_key = {"hotpotqa": "question", "hover": "claim", "ifbench": "prompt",
                         "aime2025": "problem", "livebench_math": "question"}[task.key]
            def load(split):
                if phase == "search" and split == "test":
                    raise OperationalHalt("TEST_ACCESS_DURING_SEARCH")
                ledger.event("data_split_load", split=split, task=task.key)
                path = binding["bundle"] / task.key / (split + ".jsonl")
                with path.open(encoding="utf-8") as stream:
                    return [dspy.Example(**json.loads(line, object_hook=decode_metadata)["example"])
                            .with_inputs(input_key) for line in stream]
            def metric(*args, **kwargs):
                check_time()
                return meta.metric(*args, **kwargs)
            if phase == "search":
                from gepa_artifact.gepa.gepa import GEPA
                class Log:
                    def log(self, *items):
                        check_time()
                        with (run / "native.private.log").open("a", encoding="utf-8") as stream:
                            stream.write(" ".join(map(str, items)) + "\n")
                if meta.feedback_fn_maps:
                    feedback = meta.feedback_fn_maps[0]
                else:
                    def feedback_fn(predictor_output, predictor_inputs, module_inputs, module_outputs, captured_trace):
                        value = meta.metric_with_feedback(module_inputs, module_outputs, None)
                        return {"feedback_score": value.score, "feedback_text": value.feedback}
                    feedback = {name: feedback_fn for name, _ in program.named_predictors()}
                options = {k: v for k, v in draft()["optimizer"].items() if k in {
                    "run_linearized_gepa", "use_merge", "set_for_merge_minibatch", "track_scores_on",
                    "num_dspy_examples_per_gepa_step", "skip_perfect_score", "teacher_lm", "num_threads"}}
                engine = GEPA(metric=metric, logger=Log(), run_dir=str(run / "native"),
                              named_predictor_to_feedback_fn_map=feedback, knowledgebase_qe=None,
                              max_metric_calls=task.budget, seed=0, use_wandb=False, **options)
                program = engine.compile(program, trainset=load("train"), valset=load("validation"))
                program.save(str(run / "selected_program.json"))
                result.update(selected_program_sha256=file_hash(run / "selected_program.json"),
                              native_counter=engine.gepa_state.total_num_evals)
            else:
                if phase == "final_test":
                    selected = within(workspace / grant["selected_program"], workspace)
                    if file_hash(selected) != grant.get("selected_program_sha256"):
                        raise ValueError("FROZEN_SELECTED_PROGRAM_HASH_MISMATCH")
                    program.load(str(selected))
                    program.set_lm(lm)
                evaluator = dspy.Evaluate(devset=load("test"), metric=metric, num_threads=grant["final_eval_threads"],
                                          display_progress=False, max_errors=task.sizes[2] * 10,
                                          return_outputs=True, return_all_scores=True)
                score, result_triples, scores = evaluator(program)
                predictions = [prediction for _, prediction, _ in result_triples]
                result.update(score=score, test_rows=len(scores))
                (run / "test_profile.private.json").write_bytes(canonical({"scores": scores,
                    "predictions": [dict(x) for x in predictions]}) + b"\n")
        futures.drain()
        check_time()
        validate_grant(root, workspace, grant)
        result["status"] = "COMPLETE"
    except BaseException as exc:
        result["failure_category"] = type(exc).__name__
        if isinstance(exc, OperationalHalt):
            result["operational_halt"] = str(exc)
        raise
    finally:
        try:
            if not futures.summary()["drained"]:
                futures.drain()
        except BaseException as exc:
            result.update(status="ABORTED", failure_category=type(exc).__name__)
            if isinstance(exc, OperationalHalt):
                result["operational_halt"] = str(exc)
            raise
        finally:
            futures.restore()
            if restore_meter is not None:
                restore_meter()
            if original is not None:
                import litellm
                litellm.completion = original
            result.update(actual_logical_evaluations=ledger.logical, physical_attempts=ledger.physical,
                          tokens=ledger.tokens, failed_attempts_with_unknown_usage=ledger.unknown_failed_usage,
                          phase_futures=futures.summary())
            (run / "receipt.json").write_bytes(canonical(result) + b"\n")
    return result
