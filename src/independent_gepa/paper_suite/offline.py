"""Deterministic source/data/program/scoring checks. No real LM construction."""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import importlib
import importlib.metadata
import json
from pathlib import Path
import sys
import types

from .contract import TASKS, draft
from .data import author_splits, canonical, decode_metadata, digest, load_asset_rows
from .sources import audit, syntax_node, file_hash
from .windows import install, load_livebench_sources


def load_author_function(path: Path, name: str, namespace: dict):
    node = syntax_node(path, name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


def verify_nlp():
    import nltk
    import spacy
    import spacy.cli
    for resource in ("tokenizers/punkt_tab/english", "taggers/averaged_perceptron_tagger_eng", "corpora/stopwords"):
        nltk.data.find(resource)
    spacy.load("en_core_web_sm")
    # Author files redundantly download resources at module import and while
    # checking answers. Only suppress this network activity after verifying all
    # exact local resources. No check_following/build_description is replaced.
    def local_download(name, *args, **kwargs):
        allowed = {"punkt_tab", "punkt", "averaged_perceptron_tagger_eng", "stopwords"}
        if name not in allowed:
            raise ValueError("UNPREPARED_NLTK_RESOURCE")
        return True
    nltk.download = local_download
    def local_spacy(name, *args, **kwargs):
        if name != "en_core_web_sm":
            raise ValueError("UNPREPARED_SPACY_RESOURCE")
        spacy.load(name)
    spacy.cli.download = local_spacy


def math_parity(artifact):
    modules = load_livebench_sources(artifact)
    amp = modules["AMPS_Hard.utils"]
    metric = modules["metric"].calculate_livebench_score
    cases = []
    for gold, output in [("2", r"\boxed{2}"), ("2", r"\boxed{3}"),
                         (r"\frac{1}{2}", r"\boxed{0.5}"), ("x+x", r"\boxed{2x}"),
                         ("2", "$x=2$"), ("2", "Answer: 2"), ("2", "no answer"),
                         ("2", r"\boxed{2}+C"), ("2", r"\boxed{2}\boxed{3}")]:
        cases.append(({"question_id": "synthetic", "task": "math", "category": "math",
                       "subtask": "amps_hard", "turns": ["Synthetic expression"], "ground_truth": gold}, output))
    for subtask, gold, outputs in [("aime", "42", ["42", r"\boxed{42}", "43", "no answer"]),
                                    ("amc", "B", ["BBBBB", r"\boxed{B}", "A", "no answer"]),
                                    ("imo", "1,2,3", ["1,2,3", "1,3,2", "1,2", "no answer"])]:
        for output in outputs:
            cases.append(({"question_id": "synthetic", "task": "math", "category": "math",
                           "subtask": subtask, "turns": ["Synthetic choice $A) 1$ $B) 2$ $C) 3$ $D) 4$ $E) 5$"],
                           "ground_truth": gold}, output))
    # Compare against the unmodified author's scoring functions in-process.
    # This is a result/feedback oracle, not a claim of cross-OS deadline parity.
    amp.run_with_timeout = lambda func, args=(), timeout=8: func(*args)
    reference = [metric(deepcopy(q), answer, debug=False) for q, answer in cases]
    install(artifact)
    actual = [metric(deepcopy(q), answer, debug=False) for q, answer in cases]
    if actual != reference:
        raise AssertionError("WINDOWS_AUTHOR_SCORING_OR_FEEDBACK_PARITY_FAILED")
    return {"cases": len(cases), "result_and_feedback_mismatches": 0,
            "reference": "same unmodified author scoring bodies; direct execution",
            "limitation": "not a Linux timing oracle; Windows spawn startup contributes to the original 8s wall deadline"}


def native_smoke(artifact, output, dspy):
    from gepa_artifact.gepa.gepa import GEPA
    from .control import Ledger, install_transport, install_logical_meter
    import litellm
    from .models import create_role_lms, physical_guard, role_route
    from .control import request_role
    output.mkdir(parents=True, exist_ok=False)
    meter = Ledger(output / "synthetic_ledger.jsonl", 100, 100)
    original_completion = litellm.completion
    reflections = [0]
    attempts = [0]
    environment = {"OPENLUX_API_KEY": "synthetic-solver-key", "OPENLUX_BASE_URL": "https://solver.invalid/v1",
                   "LWJ_DASHSCOPE_API_KEY": "synthetic-reflection-key", "LWJ_DASHSCOPE_BASE_URL": "https://reflection.invalid/v1"}
    observed_models = set()
    def fake_completion(**kwargs):
        attempts[0] += 1
        role = request_role(kwargs["messages"])
        route = role_route(role)
        if (kwargs["model"] != route["model"] or kwargs["api_base"] != environment[route["base_env"]]
                or kwargs["api_key"] != environment[route["key_env"]]):
            raise AssertionError("ROLE_MODEL_PROVIDER_OR_KEY_DRIFT")
        observed_models.add((role, kwargs["model"]))
        if attempts[0] == 1:
            raise TimeoutError("synthetic transient provider failure")
        if kwargs["temperature"] != 1.0 or kwargs["max_tokens"] != 16384:
            raise AssertionError("FROZEN_PROVIDER_WIRE_DRIFT")
        messages = kwargs["messages"]
        if len(messages) == 1 and messages[0]["role"] == "user":
            reflections[0] += 1
            text = "```\nSYNTHETIC_IMPROVED. Return one.\n```"
        else:
            improved = "SYNTHETIC_IMPROVED" in messages[0]["content"]
            text = "[[ ## reasoning ## ]]\nSynthetic reasoning.\n[[ ## answer ## ]]\n" + ("1" if improved else "0") + "\n[[ ## completed ## ]]"
        return litellm.ModelResponse(model="synthetic", choices=[{"message": {"role": "assistant", "content": text},
                     "finish_reason": "stop"}], usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                     system_fingerprint="synthetic")
    litellm.completion = fake_completion
    install_transport(litellm, meter, output / "synthetic_responses")
    litellm.completion = physical_guard(litellm.completion, ["solver", "reflection"], environment, lambda: None)
    class Log:
        def log(self, *args):
            pass
    calls = [0]
    def value(example, prediction, trace=None):
        calls[0] += 1
        if calls[0] > 100:
            raise KeyboardInterrupt("SYNTHETIC_NATIVE_SMOKE_DID_NOT_TERMINATE")
        return int(prediction.answer == example.answer)
    def feedback(**kwargs):
        return {"feedback_score": value(kwargs["module_inputs"], kwargs["module_outputs"]),
                "feedback_text": "Synthetic answer should be one."}
    metric = value
    program = dspy.ChainOfThought("question -> answer")
    restore_meter = install_logical_meter(type(program), meter)
    lms = create_role_lms(dspy, ["solver", "reflection"], environment)
    program.set_lm(lms["solver"])
    optimizer = GEPA(named_predictor_to_feedback_fn_map={"predict": feedback}, knowledgebase_qe=None,
                     metric=metric, logger=Log(), run_dir=str(output / "native"), run_linearized_gepa=False,
                     use_merge=False, set_for_merge_minibatch="val", track_scores_on="val",
                     max_metric_calls=10, num_threads=1, seed=0, use_wandb=False)
    train = [dspy.Example(question=f"synthetic_train_{i}", answer="1").with_inputs("question") for i in range(6)]
    validation = [dspy.Example(question=f"synthetic_validation_{i}", answer="1").with_inputs("question") for i in range(4)]
    try:
        result = optimizer.compile(program, trainset=train, valset=validation)
        reflection_entry = lms["reflection"].history[-1]
        paid_before = meter.physical
        cached = lms["reflection"](reflection_entry["prompt"], max_tokens=16384)
        if cached != reflection_entry["outputs"] or meter.physical != paid_before:
            raise AssertionError("EXACT_REFLECTION_CACHE_REUSE_FAILED")
        result.save(str(output / "selected.private.json"))
        serialized = (output / "selected.private.json").read_text(encoding="utf-8")
        if any(environment[name] in serialized for name in ("OPENLUX_API_KEY", "LWJ_DASHSCOPE_API_KEY")):
            raise AssertionError("ROLE_CREDENTIAL_SAVED_IN_PROGRAM")
        reloaded = program.deepcopy()
        reloaded.load(str(output / "selected.private.json"))
        if reloaded.get_lm().model != role_route("solver")["model"]:
            raise AssertionError("SAVED_SOLVER_MODEL_BINDING_LOST")
    finally:
        restore_meter()
        litellm.completion = original_completion
    state = optimizer.gepa_state
    if len(state.program_candidates) < 2 or state.program_full_scores_val_set[-1] != 100.0:
        raise AssertionError("NATIVE_SYNTHETIC_UPDATE_WAS_NOT_OBSERVED")
    if meter.logical != state.total_num_evals or meter.tokens["solver"]["prompt"] != meter.logical:
        raise AssertionError("NATIVE_TRANSPORT_LEDGER_CONSERVATION_FAILED")
    if meter.unknown_failed_usage != 1 or meter.physical != meter.logical + reflections[0] + 1:
        raise AssertionError("NATIVE_TRANSPORT_RETRY_ACCOUNTING_FAILED")
    if (observed_models != {(role, role_route(role)["model"]) for role in ("solver", "reflection")}
            or result.get_lm().model != role_route("solver")["model"]
            or meter.tokens["reflection"]["prompt"] != reflections[0]):
        raise AssertionError("NATIVE_ROLE_BINDING_FAILED")
    # Actual author's cache-key implementation, above physical transport.
    # Even identical messages must separate the two role models.
    message = [{"role": "user", "content": "Synthetic role cache identity"}]
    request_a = {"model": lms["solver"].model, "messages": message, **lms["solver"].kwargs}
    request_b = {"model": lms["reflection"].model, "messages": message, **lms["reflection"].kwargs}
    if dspy.cache.cache_key(request_a, ["api_key", "api_base", "base_url"]) == dspy.cache.cache_key(request_b, ["api_key", "api_base", "base_url"]):
        raise AssertionError("ROLE_MODEL_CACHE_COLLISION")
    return {"candidate_count": len(state.program_candidates), "native_counter": state.total_num_evals,
            "independent_logical_meter": meter.logical, "fake_physical_dispatches": meter.physical,
            "recovered_transient_failures": meter.unknown_failed_usage,
            "reflection_calls": reflections[0], "test_access": False,
            "role_models": dict(observed_models), "model_cache_keys_distinct": True,
            "exact_reflection_cache_reuse": True, "saved_solver_binding_without_credentials": True,
            "native_teacher_lm": optimizer.teacher_lm,
            "native_engine": "unmodified gepa_artifact.gepa.gepa.GEPA"}


def native_failure_smoke(output, dspy):
    from gepa_artifact.gepa.gepa import GEPA
    from .control import Ledger, OperationalHalt, install_transport, install_logical_meter
    import litellm
    output.mkdir(parents=True, exist_ok=False)
    meter = Ledger(output / "synthetic_ledger.jsonl", 10, 10)
    original = litellm.completion
    class Failure(Exception):
        status_code = 401
    def fail(**kwargs):
        raise Failure("synthetic unauthorized provider response")
    litellm.completion = fail
    install_transport(litellm, meter, output / "synthetic_responses")
    lm = dspy.LM(draft()["models"]["solver"], api_key="offline-failure", temperature=1.0, max_tokens=16384, num_retries=0)
    dspy.configure(lm=lm, adapter=dspy.ChatAdapter())
    class Log:
        def log(self, *items):
            pass
    program = dspy.ChainOfThought("question -> answer")
    restore_meter = install_logical_meter(type(program), meter)
    score_calls = []
    def metric(ex, pred, trace=None):
        score_calls.append(1)
        return 0
    engine = GEPA(metric=metric, logger=Log(),
                  run_dir=str(output / "native"), named_predictor_to_feedback_fn_map={}, knowledgebase_qe=None,
                  max_metric_calls=1, run_linearized_gepa=False, use_merge=False,
                  set_for_merge_minibatch="val", track_scores_on="val", use_wandb=False, num_threads=1)
    examples = [dspy.Example(question="synthetic_failure", answer="1").with_inputs("question")]
    try:
        try:
            engine.compile(program, trainset=examples, valset=examples)
        except OperationalHalt:
            if meter.physical != 1 or meter.logical != 1 or score_calls:
                raise AssertionError("NATIVE_FAILURE_WAS_RETRIED_OR_SCORED")
        else:
            raise AssertionError("NATIVE_ENGINE_SWALLOWED_OPERATIONAL_FAILURE")
    finally:
        restore_meter()
        litellm.completion = original
    return {"nontransient_attempts": 1, "logical_scores_emitted": 0, "escaped_native_exception_handler": True}


def program_smokes(modules, dspy, artifact, meter_root):
    """Execute original graphs with fake LMs and a synthetic retrieval result."""
    runs = {}
    from .control import Ledger, install_logical_meter
    meter_root.mkdir(parents=True, exist_ok=False)
    for key, answers, inputs, expected in [
        ("hotpotqa", [{"summary": "one"}, {"query": "two"}, {"summary": "two"}, {"answer": "one"}],
         {"question": "Synthetic question"}, [7, 7]),
        ("hover", [{"summary": "one"}, {"query": "two"}, {"summary": "two"}, {"query": "three"}],
         {"claim": "Synthetic claim"}, [7, 7, 10]),
        ("ifbench", [{"response": "draft"}, {"final_response": "alpha beta"}],
         {"prompt": "Synthetic constraints"}, []),
        ("aime2025", [{"answer": "42"}], {"problem": "Synthetic problem"}, []),
        ("livebench_math", [{"answer": "42"}], {"question": "Synthetic question"}, []),
    ]:
        module = modules[key]
        program = module.benchmark[0].program[0].deepcopy()
        lm = dspy.utils.DummyLM([{"reasoning": "Synthetic reasoning", **x} for x in answers])
        unused_reflection = dspy.utils.DummyLM([])
        dspy.configure(lm=unused_reflection, adapter=dspy.ChatAdapter())
        program.set_lm(lm)
        retrievals = []
        def retrieve(k):
            def call(query):
                retrievals.append(k)
                return dspy.Prediction(passages=["Synthetic | A synthetic passage."])
            return call
        if key in {"hotpotqa", "hover"}:
            program.retrieve_k = retrieve(7)
        if key == "hover":
            program.retrieve_10 = retrieve(10)
        meter = Ledger(meter_root / (key + ".jsonl"), 10, 100)
        restore = install_logical_meter(type(program), meter)
        try:
            measured_prediction = program(**inputs)
        finally:
            restore()
        if retrievals != expected or len(lm.history) != len(answers) or unused_reflection.history:
            raise AssertionError("ORIGINAL_PROGRAM_FLOW_MISMATCH:" + key)
        if meter.logical != 1:
            raise AssertionError("ONE_ROOT_EXAMPLE_MUST_NOT_COUNT_NESTED_MODULES:" + key)
        runs[key] = {"solver_calls": len(lm.history), "retrieval_k": list(retrievals), "logical_root_attempts": 1,
                     "reflection_calls_during_solver_program": len(unused_reflection.history)}
        retrievals.clear()
        reference_lm = dspy.utils.DummyLM([{"reasoning": "Synthetic reasoning", **x} for x in answers])
        program.set_lm(reference_lm)
        dspy.configure(lm=reference_lm, adapter=dspy.ChatAdapter())
        direct_prediction = program(**inputs)
        if canonical(dict(direct_prediction)) != canonical(dict(measured_prediction)) or retrievals != expected:
            raise AssertionError("METER_CHANGED_AUTHOR_PROGRAM_OUTPUT:" + key)
    ifbench = modules["ifbench"]
    ex = dspy.Example(prompt="Synthetic", instruction_id_list=["keywords:existence", "keywords:forbidden_words"],
                      kwargs=[{"keywords": ["alpha"]}, {"forbidden_words": ["beta"]}])
    if ifbench.metric(ex, dspy.Prediction(response="alpha beta")) != 0.5:
        raise AssertionError("IFBENCH_MUST_USE_AUTHOR_FRACTIONAL_LOOSE_SCORE")
    aime = modules["aime2025"]
    if aime.metric({"answer": "42"}, dspy.Prediction(answer="42")) != 1:
        raise AssertionError("AIME_AUTHOR_INTEGER_MATCH_FAILED")
    if aime.metric({"answer": "42"}, dspy.Prediction(answer=r"\boxed{42}")) != 0:
        raise AssertionError("AIME_MUST_NOT_USE_HISTORICAL_BOXED_SCORER")
    # Bind the transport in the ACTUAL program metric graph as well as in the
    # isolated differential oracle above. The scoring bodies remain upstream.
    amp = importlib.import_module("gepa_artifact.benchmarks.livebench_math.livebenchmath_utils.AMPS_Hard.utils")
    install(artifact, author_module=amp)
    live = modules["livebench_math"]
    q = {"question_id": "synthetic", "task": "math", "category": "math", "subtask": "amps_hard",
         "turns": ["Synthetic"], "ground_truth": "x+x"}
    if live.metric({"question_d": q}, dspy.Prediction(answer=r"\boxed{2x}")) != 1:
        raise AssertionError("WINDOWS_TRANSPORT_NOT_BOUND_TO_ACTUAL_METRIC_GRAPH")
    return runs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--control-only", action="store_true")
    parser.add_argument("--data-only", action="store_true")
    parser.add_argument("--program-only", action="store_true")
    parser.add_argument("--lifecycle-only", action="store_true")
    parser.add_argument("--concurrency-only", action="store_true")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    artifact = workspace / "upstream/gepa-artifact"
    receipt = {"source_audit": audit(workspace / "upstream"), "MODEL_API_CALLS": 0}
    sys.path.insert(0, str(workspace / "upstream/dspy-study"))
    sys.path.insert(0, str(artifact))
    import dspy
    if not Path(dspy.__file__).resolve().is_relative_to(workspace / "upstream/dspy-study"):
        raise ValueError("AUTHOR_DSPY_IMPORT_MISMATCH")
    if args.concurrency_only:
        from .concurrency_check import verify_concurrency
        receipt["concurrency"] = verify_concurrency(workspace, args.output.parent / (args.output.stem + "_fixture"))
        args.output.write_bytes(canonical(receipt) + b"\n")
        print(json.dumps({"status": "OFFLINE_CONCURRENCY_PASS", "API_CALLS": 0}))
        return
    if args.lifecycle_only:
        from .lifecycle_check import verify_lifecycle
        receipt["synthetic_lifecycle"] = verify_lifecycle(workspace, args.output.parent / (args.output.stem + "_fixture"))
        with args.output.open("xb") as stream:
            stream.write(canonical(receipt) + b"\n")
        print(json.dumps({"status": "OFFLINE_PHASE_LIFECYCLE_PASS", "API_CALLS": 0}))
        return
    if args.control_only:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        receipt["native_smoke"] = native_smoke(artifact, args.output.parent / (args.output.stem + "_native_fake"), dspy)
        receipt["native_failure_smoke"] = native_failure_smoke(args.output.parent / (args.output.stem + "_failure_fake"), dspy)
        with args.output.open("xb") as stream:
            stream.write(canonical(receipt) + b"\n")
        print(json.dumps({"status": "OFFLINE_NATIVE_CONTROL_PASS", "API_CALLS": 0}))
        return
    verify_nlp()
    if args.program_only:
        modules = {task.key: importlib.import_module("gepa_artifact.benchmarks." + task.package) for task in TASKS}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        receipt["fake_program_flows"] = program_smokes(modules, dspy, artifact,
                  args.output.parent / (args.output.stem + "_program_meters"))
        with args.output.open("xb") as stream:
            stream.write(canonical(receipt) + b"\n")
        print(json.dumps({"status": "OFFLINE_PROGRAM_METER_PARITY_PASS", "API_CALLS": 0}))
        return
    if not args.data_only:
        receipt["windows_math_parity"] = math_parity(artifact)
    rows = load_asset_rows(workspace / "assets")
    first = author_splits(artifact, rows)
    second = author_splits(artifact, rows, example_class=dspy.Example)
    if canonical(first) != canonical(second):
        raise AssertionError("DATA_STORAGE_ADAPTER_PARITY_FAILED")
    receipt["data_storage_parity"] = {"examples": sum(len(x) for t in first.values() for x in t.values()),
                                      "mismatches": 0, "ordered_payload_sha256": digest(first)}
    # IFBench's complete original class (including inherited random trimming)
    # separately checks the small data-only preparation implementation.
    ifmod = importlib.import_module("gepa_artifact.benchmarks.IFBench")
    benchmark = ifmod.IFBench()
    original_if = {"train": [dict(x) for x in benchmark.train_set],
                   "validation": [dict(x) for x in benchmark.val_set], "test": [dict(x) for x in benchmark.test_set]}
    if canonical(original_if) != canonical(first["ifbench"]):
        raise AssertionError("ORIGINAL_IFBENCH_LOADER_PARITY_FAILED")
    from datasets import ClassLabel
    labels = ClassLabel(names=["NOT_SUPPORTED", "SUPPORTED"])
    if labels.str2int(["NOT_SUPPORTED", "SUPPORTED"]) != [0, 1]:
        raise AssertionError("HF_HOVER_CLASSLABEL_ENCODING_MISMATCH")
    receipt["hf_hover_classlabel_parity"] = True
    if args.data_only:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as stream:
            stream.write(canonical(receipt) + b"\n")
        print(json.dumps({"status": "OFFLINE_DATA_PARITY_PASS", "API_CALLS": 0}))
        return
    programs = {}
    modules = {}
    for task in TASKS:
        module = importlib.import_module("gepa_artifact.benchmarks." + task.package)
        modules[task.key] = module
        meta = module.benchmark[0]
        program = meta.program[0]
        predictors = program.named_predictors()
        if len(predictors) != task.predictors:
            raise AssertionError("AUTHOR_PROGRAM_GRAPH_MISMATCH:" + task.key)
        programs[task.key] = {"predictors": [name for name, _ in predictors],
                               "instructions_sha256": digest({name: p.signature.instructions for name, p in predictors}),
                               "metric_module": meta.metric.__module__}
    receipt["programs"] = programs
    args.output.parent.mkdir(parents=True, exist_ok=True)
    receipt["fake_program_flows"] = program_smokes(modules, dspy, artifact,
                  args.output.parent / (args.output.stem + "_program_meters"))
    receipt["native_smoke"] = native_smoke(artifact, args.output.parent / (args.output.stem + "_native_fake"), dspy)
    receipt["dependencies"] = {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()}
    with args.output.open("xb") as f:
        f.write(canonical(receipt) + b"\n")
    print(json.dumps({"status": "OFFLINE_INTEGRATION_PASS", "API_CALLS": 0}))


if __name__ == "__main__":
    main()
