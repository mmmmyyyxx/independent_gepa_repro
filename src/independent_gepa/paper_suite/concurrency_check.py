"""Native-tail/cache and real process lifecycle probes using synthetic inputs."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

from .control import Ledger, Transport
from .data import canonical
from .execution import PhaseFutures, execution_policy
from .scheduling import Cell, ProcessJob, _run_queue
from .sources import file_hash


def verify_retrieval_mmap(workspace: Path) -> dict:
    """Compare complete-index loader/query behavior without loading Test rows."""
    import bm25s
    import gc
    import numpy as np
    import Stemmer
    root = workspace / "retrieval"
    receipt = json.loads((root / "index_receipt.json").read_text(encoding="utf-8"))
    assert receipt["index_ready"]
    for name, expected in receipt["index_files"].items():
        assert file_hash(root / "bm25s_retriever" / name) == expected
    assert file_hash(root / "wiki.abstracts.2017.jsonl") == receipt["corpus_sha256"]
    queries = ["Alan Turing", "Pacific Ocean", "United Nations 1945", "solar system", "mathematical logic", "ancient Rome"]
    stemmer = Stemmer.Stemmer("english")
    cases = [(text, k) for text in queries for k in (7, 10)]
    def query(engine, case):
        text, k = case
        tokens = bm25s.tokenize(text, stopwords="en", stemmer=stemmer, show_progress=False)
        return engine.retrieve(tokens, k=k, n_threads=1, show_progress=False)
    reference = bm25s.BM25.load(str(root / "bm25s_retriever"))
    answers = [query(reference, case) for case in cases]
    del reference
    gc.collect()
    mapped = bm25s.BM25.load(str(root / "bm25s_retriever"), mmap=True)
    assert isinstance(mapped.scores["data"], np.memmap)
    with ThreadPoolExecutor(max_workers=2) as pool:
        observed = list(pool.map(lambda case:query(mapped, case), cases))
    for expected, actual in zip(answers, observed):
        assert all(np.array_equal(a, b) for a, b in zip(expected, actual))
    return {"full_index_documents": receipt["documents"], "concurrent_queries": 2,
            "query_k_cases": len(cases), "bitwise_score_or_document_mismatches": 0,
            "all_index_file_hashes_and_corpus_hash_verified": True, "test_rows_accessed": False}


def verify_concurrency(workspace: Path, output: Path) -> dict:
    import dspy
    import dspy.utils.parallelizer as parallelizer
    import psutil
    from dspy.clients.cache import Cache, request_cache

    output.mkdir(parents=True, exist_ok=False)
    ledger = Ledger(output / "native_fake_ledger.jsonl", 20, 20)
    registry = PhaseFutures(ledger)
    registry.install(parallelizer)
    release, finished = threading.Event(), threading.Event()
    calls, lock = [], threading.Lock()
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
                               choices=[SimpleNamespace(finish_reason="stop")], model="synthetic")
    transport = Transport(lambda **kwargs: response, ledger)
    def fake(item):
        ledger.reserve_logical()
        with lock:
            ordinal = calls.count(item) + 1
            calls.append(item)
        if item == "slow" and ordinal == 1:
            assert release.wait(5)
        elif item == "fast":
            time.sleep(.025)
        transport(messages=[{"role": "system", "content": "Synthetic"}, {"role": "user", "content": item}])
        if item == "slow" and ordinal == 1:
            finished.set()
        return item + str(ordinal)
    original_time = parallelizer.time
    parallelizer.time = SimpleNamespace(time=lambda: time.monotonic() * 1000000)
    try:
        result = parallelizer.ParallelExecutor(num_threads=2, disable_progress_bar=True).execute(fake, ["slow", "fast"])
        assert result == ["slow2", "fast1"] and not finished.is_set()
        release.set()
        registry.drain()
    finally:
        release.set()
        if not registry.summary()["drained"]:
            registry.drain()
        registry.restore()
        parallelizer.time = original_time
    assert finished.is_set() and ledger.logical == ledger.physical == 3
    assert ledger.tokens["solver"] == {"prompt": 3, "completion": 3}
    assert registry.summary()["pending"] == 0
    saved_cache, barrier, draws = dspy.cache, threading.Barrier(2), []
    dspy.cache = Cache(False, True, str(output / "unused_cache"))
    @request_cache(cache_arg_name="request")
    def cached(*, request):
        barrier.wait(timeout=3)
        with lock:
            draws.append(1)
            return {"synthetic_draw": len(draws)}
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(cached, request={"synthetic": "same"}) for _ in range(2)]
            answers = [f.result(5) for f in futures]
        assert answers[0] != answers[1] and cached(request={"synthetic": "same"}) in answers and len(draws) == 2
    finally:
        dspy.cache = saved_cache
    source, private = output / "synthetic_source", output / "synthetic_workspace"
    (source / "scripts").mkdir(parents=True)
    private.mkdir()
    # The ordinary ProcessJob launches this fake script in a fresh interpreter.
    # No production grant validation is bypassed in an executable runner.
    (source / "scripts/run_gepa_paper_suite.py").write_text(
        "import argparse,hashlib,json,os,subprocess,sys,time\nfrom pathlib import Path\n"
        "p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path);p.add_argument('--authorization',type=Path);p.add_argument('--dispatch-ready',type=Path);a=p.parse_args()\n"
        "temp=a.dispatch_ready.with_suffix('.request.partial');temp.write_text(json.dumps({'pid':os.getpid(),'authorization_sha256':hashlib.sha256(a.authorization.read_bytes()).hexdigest()}));temp.replace(a.dispatch_ready.with_suffix('.request.json'))\n"
        "deadline=time.monotonic()+10\n"
        "while not a.dispatch_ready.exists() and time.monotonic()<deadline:time.sleep(.01)\n"
        "assert json.loads(a.dispatch_ready.read_text())['pid']==os.getpid()\n"
        "g=json.loads(a.authorization.read_text());assert g['real_api_allowed'] is False\n"
        "if g.get('tree'):\n"
        " c=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);(a.workspace/g['pidfile']).write_text(str(c.pid))\n"
        " if not g.get('orphan'):time.sleep(60)\n"
        "else:\n"
        " time.sleep(.05);(a.workspace/(g['task']+'.json')).write_text(json.dumps({'pid':os.getpid(),'score':0}))\n",
        encoding="utf-8")
    settings = {**execution_policy()["scheduler"], "poll_seconds": .01}
    cells, jobs = [], []
    for key in settings["task_order"]:
        path = private / (key + ".grant.json")
        grant = {"task": key, "real_api_allowed": False, "max_elapsed_seconds": 15}
        path.write_bytes(canonical(grant))
        cells.append(Cell(key, path, grant))
    def start(cell):
        job = ProcessJob(cell, source, private, output)
        jobs.append(job)
        return job
    def verify(cell):
        return json.loads((private / (cell.task + ".json")).read_text())
    completed = _run_queue(cells, settings, time.monotonic()+30, start=start, verify=verify,
                          available=lambda: 30*1024**3, event=lambda *args, **kwargs: None)
    assert len(completed) == 5 and len({x["pid"] for x in completed}) == 5
    assert all(x["score"] == 0 for x in completed) and all(job.poll() == 0 for job in jobs)
    path = private / "tree.grant.json"
    path.write_bytes(canonical({"tree": True, "pidfile": "child.pid", "real_api_allowed": False}))
    tree_job = ProcessJob(Cell("tree", path, {}), source, private, output)
    try:
        until = time.monotonic()+10
        while not (private / "child.pid").exists() and time.monotonic() < until:
            time.sleep(.02)
        child = int((private / "child.pid").read_text())
    finally:
        tree_job.stop()
        tree_job.close()
    assert tree_job.poll() is not None and not psutil.pid_exists(child)
    orphan_path = private / "orphan.grant.json"
    orphan_path.write_bytes(canonical({"tree": True, "orphan": True, "pidfile": "orphan.pid", "real_api_allowed": False}))
    orphan_job = ProcessJob(Cell("orphan", orphan_path, {}), source, private, output)
    try:
        until = time.monotonic()+10
        while orphan_job.poll() is None and time.monotonic() < until:
            time.sleep(.02)
        assert orphan_job.poll() == 0
        orphan = psutil.Process(int((private / "orphan.pid").read_text()))
        assert orphan.is_running()
    finally:
        orphan_job.close()
    _, alive = psutil.wait_procs([orphan], timeout=3)
    assert not alive
    return {"native_tail_duplicate_still_wins": True, "native_fake_items": 2,
            "actual_fake_logical_and_physical_attempts": 3, "late_usage_preserved": True,
            "phase_futures": registry.summary(), "native_concurrent_cache_misses_dispatches": 2,
            "separate_phase_processes_completed": 5, "zero_scores_do_not_change_schedule": True,
            "real_parent_and_descendant_cleanup": True, "model_api_calls": 0,
            "descendant_cleanup_after_parent_exit": True,
            "retrieval_mmap": verify_retrieval_mmap(workspace),
            "test_clock_accelerated_only": True,
            "limitation": "synthetic process script is not a real API authorization or throughput benchmark"}
