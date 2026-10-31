"""Versioned execution policy around the unchanged author search algorithm."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
import json
from pathlib import Path
import threading
import time

from .contract import IDENTITY
from .control import OperationalHalt
from .data import canonical
from .sources import file_hash


POLICY_PATH = "configs/gepa_paper_execution_concurrency_v1.json"
GRANT_SCHEMA = IDENTITY + "_authorization_v2"


def execution_policy() -> dict:
    return {
        "schema": "gepa_paper_execution_concurrency_v1",
        "native_search_threads": "os.cpu_count; exact resolved count bound by grant",
        "final_eval_threads": 32,
        "retrieval_mmap": True,
        "native_tail_resubmission": "unchanged; drain all submitted futures at phase exit",
        "concurrent_cache_misses": "unchanged; no single-flight or deduplication",
        "scheduler": {
            "max_parallel_phases": 2, "retrieval_slots": 1, "nonretrieval_slots": 1,
            "retrieval_tasks": ["hover", "hotpotqa"],
            "task_order": ["hover", "hotpotqa", "ifbench", "aime2025", "livebench_math"],
            "exclusive_tasks": ["livebench_math"],
            "stages": ["search", "baseline", "final_test"],
            "memory_reservation_gib": {"retrieval": 5, "nonretrieval": 1, "livebench_math": 2},
            "memory_headroom_gib": 1,
            "idle_resource_wait_seconds": 3600, "poll_seconds": 2,
            "failed_child": "abort stage; terminate process trees; preserve evidence; never retry scope",
            "provider_rpm_tpm": "unverified; no new rate limit or changed native worker count",
        },
    }


def load_execution_policy(root: Path) -> dict:
    policy = json.loads((root / POLICY_PATH).read_text(encoding="utf-8"))
    if canonical(policy) != canonical(execution_policy()):
        raise ValueError("UNIMPLEMENTED_PAPER_EXECUTION_POLICY")
    return policy


def execution_binding(root: Path, search_threads: int) -> dict:
    if type(search_threads) is not int or search_threads <= 0:
        raise ValueError("POSITIVE_RESOLVED_NATIVE_THREAD_COUNT_REQUIRED")
    policy = load_execution_policy(root)
    return {"execution_policy_sha256": file_hash(root / POLICY_PATH),
            "search_threads": search_threads, "final_eval_threads": policy["final_eval_threads"]}


EXECUTION_BINDINGS = ("execution_policy_sha256", "search_threads", "final_eval_threads")


class PhaseFutures:
    """Register native executor work without changing submissions or winners.

    A phase must finish all queued/running futures before unpatching transport,
    sealing accounting, or allowing its child process to report COMPLETE.
    """
    def __init__(self, ledger):
        self.ledger = ledger
        self._lock = threading.Lock()
        self._executors: list[ThreadPoolExecutor] = []
        self._pending = set()
        self.submitted = 0
        self.completed = 0
        self._fatal: BaseException | None = None
        self._original = None
        self._module = None
        self._closed = False
        self._drained = False

    def install(self, module) -> None:
        if self._module is not None:
            raise ValueError("PHASE_FUTURES_ALREADY_INSTALLED")
        owner = self
        original = module.ThreadPoolExecutor

        class RegisteredExecutor(original):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                with owner._lock:
                    owner._executors.append(self)

            def submit(self, fn, /, *args, **kwargs):
                with owner._lock:
                    if owner._closed:
                        raise OperationalHalt("PHASE_EXECUTOR_ALREADY_CLOSED")
                    future = super().submit(fn, *args, **kwargs)
                    owner._pending.add(future)
                    owner.submitted += 1
                future.add_done_callback(owner._done)
                return future

        self._original, self._module = original, module
        module.ThreadPoolExecutor = RegisteredExecutor

    def _done(self, future) -> None:
        error = None if future.cancelled() else future.exception()
        with self._lock:
            if error is not None and self._fatal is None:
                self._fatal = error
            self.completed += 1
            self._pending.discard(future)

    def drain(self) -> None:
        """Finish even losing futures; a late failure invalidates the phase.

        After the phase deadline cancel queued work, but keep the patches live
        while running workers unwind through their bounded provider timeout.
        Never seal a successful receipt while that work can still write usage.
        """
        deadline_hit = False
        while True:
            with self._lock:
                pending = list(self._pending)
            if not pending:
                break
            if self.ledger.wall_deadline is not None and time.monotonic() >= self.ledger.wall_deadline:
                deadline_hit = True
                for future in pending:
                    future.cancel()
            wait(pending, timeout=.1)
        # Join after callbacks complete, including native shutdown(wait=False).
        with self._lock:
            self._closed = True
            executors = list(self._executors)
        for executor in executors:
            executor.shutdown(wait=True)
        with self._lock:
            self._drained = True
            error = self._fatal
        self.ledger.event("phase_futures_drained", submitted=self.submitted, completed=self.completed)
        if error is not None:
            raise error
        if deadline_hit:
            raise OperationalHalt("PHASE_WALL_TIME_DURING_FUTURE_DRAIN")

    def restore(self) -> None:
        if self._module is not None:
            if not self._drained:
                raise OperationalHalt("CANNOT_RESTORE_WITH_UNDRAINED_PHASE_FUTURES")
            self._module.ThreadPoolExecutor = self._original
            self._module = None

    def summary(self) -> dict:
        with self._lock:
            return {"submitted": self.submitted, "completed": self.completed,
                    "pending": len(self._pending), "drained": self._drained,
                    "late_error_category": type(self._fatal).__name__ if self._fatal else None}
