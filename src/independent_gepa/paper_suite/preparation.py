"""Read-only launch inventory and reviewable phase plan. Never authorizes a run."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from .contract import CONFIG_PATH, IDENTITY, PROTOCOL_PATH, TASKS, draft
from .data import canonical
from .sources import audit, file_hash, git


def safe_deployment_presence(value: dict | None) -> dict:
    """Never copy caller-provided endpoint/key values into a public artifact."""
    names = ("OPENLUX_API_KEY", "OPENLUX_BASE_URL", "LWJ_DASHSCOPE_API_KEY", "LWJ_DASHSCOPE_BASE_URL")
    if value is None:
        return {"status": "NOT_CHECKED_IN_SCRUBBED_OFFLINE_ENVIRONMENT"}
    if set(value) != set(names) or any(type(value[name]) is not bool for name in names):
        raise ValueError("BOOLEAN_DEPLOYMENT_PRESENCE_ONLY")
    return {name: value[name] for name in names}


def phase_plan() -> list[dict]:
    """Proposed finite operational ceilings, inactive until exact user approval.

    Native thresholds and skip/overshoot behavior remain unchanged. The larger
    independent limit catches counter-stalling loops; crossing it aborts the
    attempt. Physical allowance includes original adapter fallback and eight
    transient retries, not additional semantic retries.
    """
    cells = [{"task": "aime2025", "phase": "canary", "seed": 0, "repeat": 1,
              "roles": ["solver", "reflection"], "max_logical_evaluations": 1,
              "max_physical_attempts": 18, "max_elapsed_seconds": 3000}]
    for phase in ("search", "baseline", "final_test"):
        for task in TASKS:
            logical = 2 * (task.budget + task.sizes[1] + 6) if phase == "search" else task.sizes[2]
            cells.append({"task": task.key, "phase": phase, "seed": 0, "repeat": 1,
                          "roles": ["solver", "reflection"] if phase == "search" else ["solver"],
                          "native_search_threshold": task.budget if phase == "search" else None,
                          "max_logical_evaluations": logical,
                          "max_physical_attempts": 9 * (2 * task.predictors + (phase == "search")) * logical,
                          "max_elapsed_seconds": 259200 if phase == "search" else 86400})
    for cell in cells:
        cell.update(approved_by=None, READY_TO_RUN=False, real_api_allowed=False, token_ceiling=None,
                    scope_id=None, source_sha=None, cache_namespace=None)
    return cells


def verify_data_files(bundle: Path, receipt: dict) -> dict:
    total = 0
    for task in TASKS:
        for split, size in zip(("train", "validation", "test"), task.sizes):
            expected = receipt["splits"][task.key][split]
            path = bundle / task.key / (split + ".jsonl")
            if file_hash(path) != expected["file_sha256"]:
                raise ValueError("LAUNCH_DATA_FILE_DRIFT:" + task.key + ":" + split)
            with path.open(encoding="utf-8") as stream:
                count = sum(1 for _ in stream)
            if count != size or expected["count"] != size:
                raise ValueError("LAUNCH_DATA_SIZE_DRIFT")
            total += count
    return {"files": 15, "rows": total, "hash_mismatches": 0}


def write_run_pack(root: Path, workspace: Path, output: Path, environment_python: Path,
                   deployment_presence: dict | None = None) -> dict:
    if output.exists():
        raise ValueError("FRESH_LAUNCH_PACK_REQUIRED")
    presence = safe_deployment_presence(deployment_presence)
    protocol = root / PROTOCOL_PATH
    manifest = json.loads((protocol / "manifest.json").read_text())
    if canonical(json.loads((root / CONFIG_PATH).read_text())) != canonical(draft()):
        raise ValueError("LAUNCH_CONFIGURATION_DRIFT")
    bindings = {"configuration_sha256": root / CONFIG_PATH,
                "environment_lock_sha256": root / "requirements/paper-suite-windows.lock.txt"}
    for name in ("source", "data", "program", "environment", "nlp"):
        bindings[name + "_inventory_sha256"] = protocol / (name + "_inventory.json")
    if any(manifest[key] != file_hash(path) for key, path in bindings.items()):
        raise ValueError("LAUNCH_MANIFEST_BINDING_DRIFT")
    if audit(workspace / "upstream") != json.loads((protocol / "source_inventory.json").read_text()):
        raise ValueError("LAUNCH_AUTHOR_SOURCE_DRIFT")
    bundle = workspace / "data_bundle_v4"
    if file_hash(bundle / "receipt.json") != manifest["data_inventory_sha256"]:
        raise ValueError("LAUNCH_DATA_RECEIPT_DRIFT")
    data = verify_data_files(bundle, json.loads((bundle / "receipt.json").read_text()))
    nlp = json.loads((protocol / "nlp_inventory.json").read_text())
    for relative, sha in nlp["files"].items():
        path = (workspace / "nlp/nltk_data" / relative).resolve()
        if not path.is_relative_to((workspace / "nlp/nltk_data").resolve()) or file_hash(path) != sha:
            raise ValueError("LAUNCH_NLP_RESOURCE_DRIFT")
    # No DSPy, LiteLLM, OpenAI or provider client is imported by this audit.
    code = ("import importlib.metadata as m,json,sys; sys.path[:0]=sys.argv[1:]; "
            "print(json.dumps({'python':list(sys.version_info[:2]),'versions':"
            "{d.metadata['Name']:d.version for d in m.distributions()}}))")
    installed = json.loads(subprocess.check_output([str(environment_python), "-I", "-c", code,
                                                   str(root / "src"), str(root / "vendor/gepa/src")], text=True))
    versions = json.loads((protocol / "environment_inventory.json").read_text())
    if installed["python"] != [3, 11] or any(installed["versions"].get(k) != v for k, v in versions.items()):
        raise ValueError("LAUNCH_INSTALLED_ENVIRONMENT_DRIFT")
    corpus_receipt = json.loads((workspace / "retrieval/corpus_receipt.json").read_text())
    if file_hash(workspace / "retrieval/wiki.abstracts.2017.jsonl") != corpus_receipt["corpus_sha256"]:
        raise ValueError("LAUNCH_WIKIPEDIA_CORPUS_DRIFT")
    index_path = workspace / "retrieval/index_receipt.json"
    index_ready = False
    if index_path.exists():
        index = json.loads(index_path.read_text())
        index_root = (workspace / "retrieval/bm25s_retriever").resolve()
        if index.get("corpus_sha256") != corpus_receipt["corpus_sha256"] or not index.get("index_ready"):
            raise ValueError("LAUNCH_RETRIEVAL_RECEIPT_DRIFT")
        for relative, sha in index["index_files"].items():
            path = (index_root / relative).resolve()
            if not path.is_relative_to(index_root) or file_hash(path) != sha:
                raise ValueError("LAUNCH_INDEX_FILE_DRIFT")
        index_ready = True
    paths = [*sorted((root / "src/independent_gepa/paper_suite").glob("*.py")),
             *sorted((root / "scripts").glob("*gepa_paper*.py")),
             *sorted((root / "tests").glob("test_gepa_paper*.py")),
             root / "tests/paper_zero_network/sitecustomize.py", root / CONFIG_PATH,
             root / "requirements/paper-suite-windows.lock.txt"]
    files = {p.relative_to(root).as_posix(): file_hash(p) for p in paths}
    summary = dict(schema="gepa_paper_launch_preparation_v1", protocol=IDENTITY,
                   READY_TO_RUN=False, real_api_allowed=False, preparation_only=True,
                   source_parent_sha=git(root, "rev-parse", "HEAD"),
                   source_worktree_clean=not bool(git(root, "status", "--porcelain")),
                   source_candidate_files=files, manifest_sha256=file_hash(protocol / "manifest.json"),
                   exact_author_sources_verified=True, data=data,
                   nlp_files_verified=len(nlp["files"]), installed_dependencies_verified=len(versions),
                   corpus_verified=True, index_ready=index_ready, bm25_build_deferred_by_user=not index_ready,
                   effective_native_search_threads=os.cpu_count(), final_eval_threads=32,
                   deployment_presence=presence,
                   exact_model_canary_complete=False, formal_authorization=False,
                   model_api_calls=0, model_tokens=0,
                   remaining=["clean committed source freeze", "OpenLux deployment variables and dual-model canary",
                              "BM25 index for HotpotQA/HoVer" if not index_ready else "exact index receipt binding",
                              "user approval of exact phase scopes and proposed operational ceilings"])
    output.mkdir(parents=True)
    (output / "preflight.json").write_bytes(canonical(summary) + b"\n")
    (output / "phase_plan.proposed.json").write_bytes(canonical({
        "status": "PROPOSAL_NOT_AUTHORIZATION", "READY_TO_RUN": False,
        "order": "canary -> all five searches and selection freezes -> baseline and selected Test; no Test feedback into search",
        "native_thresholds_total": 21193, "test_rows_total_including_baselines": 2340,
        "ceilings": "proposed safety caps only; hitting a cap aborts, never completes a scientific run",
        "cells": phase_plan()}) + b"\n")
    return summary
