"""Memory-aware process scheduling for one explicitly authorized phase stage."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Callable

from .contract import TASKS
from .control import OperationalHalt
from .data import canonical, digest
from .execution import EXECUTION_BINDINGS, POLICY_PATH, load_execution_policy
from .sources import file_hash, git
from .process_group import WindowsProcessGroup


STAGE_SCHEMA = "gepa_paper_stage_schedule_v1"


@dataclass(frozen=True)
class Cell:
    task: str
    authorization: Path
    grant: dict


def template(root: Path, workspace: Path, phase: str, grant_directory: Path) -> dict:
    policy = load_execution_policy(root)
    if phase not in policy["scheduler"]["stages"]:
        raise ValueError("PAPER_SCHEDULE_PHASE_REQUIRED")
    cells = []
    for task in policy["scheduler"]["task_order"]:
        path = (grant_directory / (task + "_" + phase + ".json")).resolve()
        if not path.is_relative_to(workspace.resolve()):
            raise ValueError("SCHEDULE_GRANTS_MUST_BE_IN_WORKSPACE")
        cells.append({"task": task, "authorization": path.relative_to(workspace.resolve()).as_posix(),
                      "authorization_sha256": file_hash(path) if path.is_file() else None})
    return {"schema": STAGE_SCHEMA, "phase": phase, "scope_id": None,
            "source_sha": None if git(root, "status", "--porcelain") else git(root, "rev-parse", "HEAD"),
            "source_parent_sha": git(root, "rev-parse", "HEAD"),
            "execution_policy_sha256": file_hash(root / POLICY_PATH), "cells": cells,
            "max_elapsed_seconds": 5 * (259200 if phase == "search" else 86400) + 3600,
            "approved_by": None, "real_api_allowed": False, "READY_TO_RUN": False}


def validate_stage(root: Path, workspace: Path, plan: dict) -> tuple[list[Cell], dict]:
    from .runtime import MODEL_BINDINGS, validate_grant, within
    if (plan.get("schema") != STAGE_SCHEMA or plan.get("approved_by") != "user"
            or plan.get("real_api_allowed") is not True or plan.get("READY_TO_RUN") is not True):
        raise ValueError("EXACT_STAGE_SCHEDULE_AUTHORIZATION_REQUIRED")
    policy = load_execution_policy(root)
    if plan.get("phase") not in policy["scheduler"]["stages"]:
        raise ValueError("PAPER_SCHEDULE_PHASE_REQUIRED")
    if (plan.get("source_sha") != git(root, "rev-parse", "HEAD")
            or git(root, "status", "--porcelain")
            or plan.get("execution_policy_sha256") != file_hash(root / POLICY_PATH)):
        raise ValueError("CLEAN_FROZEN_SCHEDULE_SOURCE_AND_POLICY_REQUIRED")
    scope = plan.get("scope_id")
    if not isinstance(scope, str) or not scope or not scope.replace("_", "").replace("-", "").isalnum():
        raise ValueError("FRESH_SCHEDULE_SCOPE_REQUIRED")
    if type(plan.get("max_elapsed_seconds")) is not int or plan["max_elapsed_seconds"] <= 0:
        raise ValueError("FINITE_STAGE_WALL_TIME_REQUIRED")
    records = plan.get("cells")
    if (not isinstance(records, list) or len(records) != len(TASKS)
            or {x.get("task") for x in records} != {t.key for t in TASKS}):
        raise ValueError("EXACT_FIVE_TASK_STAGE_REQUIRED")
    cells = []
    shared = None
    for record in records:
        path = within(workspace / record["authorization"], workspace)
        if file_hash(path) != record.get("authorization_sha256"):
            raise ValueError("FROZEN_STAGE_GRANT_HASH_MISMATCH")
        grant = json.loads(path.read_text(encoding="utf-8"))
        if grant.get("task") != record["task"] or grant.get("phase") != plan["phase"]:
            raise ValueError("SCHEDULE_CELL_IDENTITY_MISMATCH")
        validate_grant(root, workspace, grant)
        signature = {k: grant.get(k) for k in ("source_sha", "config_sha256", "data_receipt_sha256",
                     "environment_lock_sha256", "canary_receipt", "canary_receipt_sha256",
                     "search_receipts", "baseline_receipts", *MODEL_BINDINGS, *EXECUTION_BINDINGS)}
        if shared is not None and signature != shared:
            raise ValueError("SCHEDULE_CELLS_HAVE_DIFFERENT_FROZEN_BINDINGS")
        shared = signature
        cells.append(Cell(record["task"], path, grant))
    if (len({c.grant["scope_id"] for c in cells}) != len(cells)
            or len({c.grant["cache_namespace"] for c in cells}) != len(cells)):
        raise ValueError("TASK_SCOPE_AND_CACHE_ISOLATION_REQUIRED")
    return cells, policy


def reservation(cell: Cell, settings: dict) -> int:
    category = (cell.task if cell.task in settings["exclusive_tasks"] else
                "retrieval" if cell.task in settings["retrieval_tasks"] else "nonretrieval")
    return settings["memory_reservation_gib"][category] * 1024 ** 3


def admissible(cell: Cell, active: dict, settings: dict, available: int) -> bool:
    if len(active) >= settings["max_parallel_phases"]:
        return False
    if cell.task in settings["exclusive_tasks"] and active:
        return False
    if any(job.cell.task in settings["exclusive_tasks"] for job in active.values()):
        return False
    heavy = cell.task in settings["retrieval_tasks"]
    used_slots = sum((job.cell.task in settings["retrieval_tasks"]) == heavy for job in active.values())
    if used_slots >= settings["retrieval_slots" if heavy else "nonretrieval_slots"]:
        return False
    # Reserve the still-unallocated part of each admitted process's estimated
    # peak. USS excludes shared library/mmap pages; missing observations reserve
    # the whole amount, never optimistically count unavailable measurements.
    future_growth = sum(max(0, reservation(job.cell, settings) - job.private_bytes()) for job in active.values())
    return available >= future_growth + reservation(cell, settings) + settings["memory_headroom_gib"] * 1024 ** 3


def _run_queue(cells: list[Cell], settings: dict, deadline: float, *, start: Callable,
               verify: Callable, available: Callable, event: Callable,
               clock: Callable = time.monotonic, sleep: Callable = time.sleep,
               completed: list[dict] | None = None) -> list[dict]:
    order = {key: i for i, key in enumerate(settings["task_order"])}
    pending = sorted(cells, key=lambda c: order[c.task])
    active = {}
    completed = [] if completed is None else completed
    idle_since = None
    try:
        while pending or active:
            now = clock()
            if now >= deadline:
                raise OperationalHalt("STAGE_WALL_TIME_SAFETY_LIMIT")
            for key, job in list(active.items()):
                code = job.poll()
                if code is None:
                    if now - job.started >= job.cell.grant["max_elapsed_seconds"]:
                        raise OperationalHalt("CHILD_PHASE_WALL_TIME_SAFETY_LIMIT")
                    continue
                job.close()
                if code != 0:
                    raise OperationalHalt("CHILD_PHASE_FAILED:" + job.cell.task)
                receipt = verify(job.cell)
                completed.append({"task": job.cell.task, **receipt})
                del active[key]
                event("cell_complete", task=job.cell.task)
            for cell in list(pending):
                if admissible(cell, active, settings, available()):
                    job = start(cell)
                    active[cell.task] = job
                    pending.remove(cell)
                    event("cell_started", task=cell.task, active=len(active), pid=getattr(job, "pid", None))
            if not active and pending:
                idle_since = now if idle_since is None else idle_since
                if now - idle_since >= settings["idle_resource_wait_seconds"]:
                    raise OperationalHalt("SCHEDULE_RESOURCE_WAIT_LIMIT")
            else:
                idle_since = None
            if pending or active:
                sleep(settings["poll_seconds"])
    except BaseException:
        cleanup_errors = []
        for job in active.values():
            try:
                job.stop()
            except BaseException as exc:
                cleanup_errors.append(type(exc).__name__)
            try:
                job.close()
            except BaseException as exc:
                cleanup_errors.append(type(exc).__name__)
        if cleanup_errors:
            event("process_tree_cleanup_errors", categories=cleanup_errors)
        raise
    return completed


class ProcessJob:
    def __init__(self, cell: Cell, root: Path, workspace: Path, output: Path):
        self.cell = cell
        root, workspace, output = root.resolve(), workspace.resolve(), output.resolve()
        if not output.is_relative_to(workspace):
            raise ValueError("DISPATCH_OUTPUT_MUST_BE_IN_WORKSPACE")
        self.started = time.monotonic()
        self._group = None
        self._stream = (output / (cell.task + ".stdout_stderr.private.log")).open("xb")
        try:
            ready = output / (cell.task + ".dispatch_ready.json")
            self.process = subprocess.Popen([
                sys.executable, str(root / "scripts/run_gepa_paper_suite.py"),
                "--workspace", str(workspace), "--authorization", str(cell.authorization.resolve()),
                "--dispatch-ready", str(ready)],
                cwd=root, stdout=self._stream, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            self._group = WindowsProcessGroup(self.process)
            # A Windows venv executable can be a redirector with a different
            # PID from the interpreter. The child announces itself before any
            # provider creation; verify lineage and attach that PID as well.
            import psutil
            requested = ready.with_suffix(".request.json")
            deadline = time.monotonic() + 30
            while not requested.exists() and self.process.poll() is None and time.monotonic() < deadline:
                time.sleep(.02)
            if not requested.exists():
                reason = "CHILD_EXITED" if self.process.poll() is not None else "TIMEOUT"
                raise OperationalHalt("DISPATCH_HANDSHAKE_MISSING:" + reason)
            request = json.loads(requested.read_text(encoding="utf-8"))
            allowed = {self.process.pid, *(p.pid for p in psutil.Process(self.process.pid).children(recursive=True))}
            if request.get("pid") not in allowed or request.get("authorization_sha256") != file_hash(cell.authorization):
                raise OperationalHalt("DISPATCH_INTERPRETER_LINEAGE_MISMATCH")
            self._group.include(request["pid"])
            temporary = ready.with_suffix(".partial")
            with temporary.open("xb") as stream:
                stream.write(canonical(request) + b"\n")
            temporary.replace(ready)
        except BaseException:
            if getattr(self, "process", None) is not None and self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=5)
            if self._group is not None:
                self._group.close()
            self._stream.close()
            raise

    def poll(self):
        return self.process.poll()

    @property
    def pid(self):
        return self.process.pid

    def private_bytes(self) -> int:
        import psutil
        try:
            parent = psutil.Process(self.process.pid)
            return sum(p.memory_full_info().uss for p in [parent, *parent.children(recursive=True)])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return 0

    def stop(self) -> None:
        import psutil
        if os.name == "nt" and self._group is not None:
            self._group.terminate()
            self.process.wait(timeout=5)
            return
        try:
            children = psutil.Process(self.process.pid).children(recursive=True)
        except psutil.NoSuchProcess:
            children = []
        if self.process.poll() is None:
            self.process.terminate()
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(children, timeout=3)
        for child in alive:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        psutil.wait_procs(alive, timeout=3)
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)

    def close(self) -> None:
        if self._group is not None:
            self._group.close()
        self._stream.close()


def execute_stage(root: Path, workspace: Path, plan_path: Path) -> dict:
    from .runtime import MODEL_BINDINGS, within
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    cells, policy = validate_stage(root, workspace, plan)
    for cell in cells:
        if ((root / "runs/paper_authorization_consumed" / (digest(cell.grant) + ".json")).exists()
                or (workspace / "execution" / cell.grant["scope_id"]).exists()):
            raise ValueError("SCHEDULE_REQUIRES_UNUSED_CELL_SCOPES")
    output = within(workspace / "schedules" / plan["scope_id"], workspace)
    output.mkdir(parents=True, exist_ok=False)
    consumed = root / "runs/paper_schedule_consumed"
    consumed.mkdir(exist_ok=True)
    with (consumed / (digest(plan) + ".json")).open("xb") as stream:
        stream.write(canonical({"scope_id": plan["scope_id"]}) + b"\n")
    started = time.monotonic()
    result = {"schema": STAGE_SCHEMA, "phase": plan["phase"], "status": "ABORTED",
              "source_sha": plan["source_sha"], "execution_policy_sha256": plan["execution_policy_sha256"],
              "stage_plan_sha256": file_hash(plan_path), "completed": []}
    def event(kind, **values):
        with (output / "events.jsonl").open("ab") as stream:
            stream.write(canonical({"event": kind, "elapsed_seconds": time.monotonic()-started, **values}) + b"\n")
    def start(cell):
        if file_hash(cell.authorization) != next(x["authorization_sha256"] for x in plan["cells"] if x["task"] == cell.task):
            raise OperationalHalt("STAGE_GRANT_CHANGED_BEFORE_DISPATCH")
        return ProcessJob(cell, root, workspace, output)
    def verify(cell):
        receipt_path = workspace / "execution" / cell.grant["scope_id"] / "receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        keys = ("source_sha", "config_sha256", "data_receipt_sha256", "scope_id", "task", "phase",
                *MODEL_BINDINGS, *EXECUTION_BINDINGS)
        if (receipt.get("status") != "COMPLETE" or any(receipt.get(k) != cell.grant[k] for k in keys)
                or not receipt.get("phase_futures", {}).get("drained")
                or receipt["phase_futures"].get("pending") != 0):
            raise OperationalHalt("CHILD_RECEIPT_OR_DRAIN_MISMATCH")
        if (receipt["physical_attempts"] > cell.grant["max_physical_attempts"]
                or receipt["actual_logical_evaluations"] > cell.grant["max_logical_evaluations"]):
            raise OperationalHalt("CHILD_RECEIPT_BUDGET_MISMATCH")
        return {"receipt_sha256": file_hash(receipt_path)}
    try:
        import psutil
        result["completed"] = _run_queue(cells, policy["scheduler"], started+plan["max_elapsed_seconds"],
            start=start, verify=verify, available=lambda:psutil.virtual_memory().available, event=event,
            completed=result["completed"])
        # Recheck all bindings, including source/worktree/grants, after work ends.
        validate_stage(root, workspace, json.loads(plan_path.read_text(encoding="utf-8")))
        if file_hash(plan_path) != result["stage_plan_sha256"]:
            raise OperationalHalt("STAGE_PLAN_CHANGED_DURING_EXECUTION")
        result["status"] = "COMPLETE"
    except BaseException as exc:
        result["failure_category"] = type(exc).__name__
        if isinstance(exc, OperationalHalt):
            result["operational_halt"] = str(exc)
        raise
    finally:
        result["elapsed_seconds"] = time.monotonic()-started
        (output / "receipt.json").write_bytes(canonical(result) + b"\n")
    return result
