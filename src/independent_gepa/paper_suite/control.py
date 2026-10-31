"""Operational safeguards around, never inside, the original GEPA search."""
from __future__ import annotations

from dataclasses import dataclass, field
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from typing import Callable

from .data import canonical


class OperationalHalt(BaseException):
    """Bypass upstream broad except-Exception paths that otherwise score/skip failures."""


@dataclass
class Ledger:
    path: Path
    logical_ceiling: int
    physical_ceiling: int
    logical: int = 0
    physical: int = 0
    tokens: dict = field(default_factory=lambda: {
        role: {"prompt": 0, "completion": 0} for role in ("solver", "reflection")})
    unknown_failed_usage: int = 0
    wall_deadline: float | None = None
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def event(self, kind, **values):
        with self._lock:
            try:
                with self.path.open("ab") as stream:
                    stream.write(canonical({"event": kind, **values}) + b"\n")
                    stream.flush()
            except Exception:
                raise OperationalHalt("LEDGER_PERSISTENCE_FAILED") from None

    def metric(self, function):
        def measured(*args, **kwargs):
            self.reserve_logical()
            return function(*args, **kwargs)
        return measured

    def reserve_logical(self):
        with self._lock:
            self.check_deadline()
            if self.logical >= self.logical_ceiling:
                raise OperationalHalt("LOGICAL_SAFETY_CEILING; run is aborted, not a completed paper result")
            self.logical += 1
            self.event("logical_evaluation", ordinal=self.logical)

    def reserve_physical(self, role, request_hash):
        with self._lock:
            self.check_deadline()
            if self.physical >= self.physical_ceiling:
                raise OperationalHalt("PHYSICAL_SAFETY_CEILING")
            self.physical += 1
            self.event("physical_attempt", ordinal=self.physical, role=role, request_sha256=request_hash)

    def check_deadline(self):
        if self.wall_deadline is not None and time.monotonic() >= self.wall_deadline:
            raise OperationalHalt("PHASE_WALL_TIME_SAFETY_LIMIT")

    def record_response(self, role, response):
        usage = getattr(response, "usage", None)
        choices = getattr(response, "choices", None)
        if not usage or not choices:
            raise OperationalHalt("PROVIDER_RESPONSE_SCHEMA_OR_USAGE_MISSING")
        prompt = getattr(usage, "prompt_tokens", None)
        completion = getattr(usage, "completion_tokens", None)
        if not isinstance(prompt, int) or not isinstance(completion, int) or min(prompt, completion) < 0:
            raise OperationalHalt("PROVIDER_USAGE_INVALID")
        with self._lock:
            self.tokens[role]["prompt"] += prompt
            self.tokens[role]["completion"] += completion
            self.event("response", role=role, prompt_tokens=prompt, completion_tokens=completion,
                       model=getattr(response, "model", None),
                       system_fingerprint=getattr(response, "system_fingerprint", None),
                       finish_reason=getattr(choices[0], "finish_reason", None))


def transient(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status is not None:
        return status in {408, 429, 500, 502, 503, 504}
    return isinstance(exc, (TimeoutError, ConnectionError)) or type(exc).__name__ in {
        "Timeout", "ReadTimeout", "ConnectTimeout", "WriteTimeout", "PoolTimeout", "APITimeoutError",
        "APIConnectionError", "ConnectError", "ConnectionError", "ReadError", "WriteError", "RemoteProtocolError"}


def request_role(messages) -> str:
    if not messages or not isinstance(messages, list):
        raise OperationalHalt("UNEXPECTED_AUTHOR_REQUEST_INTERFACE")
    return "reflection" if len(messages) == 1 and messages[0].get("role") == "user" else "solver"


class Transport:
    """Wrap LiteLLM's physical completion call beneath DSPy's original cache."""
    def __init__(self, original: Callable, ledger: Ledger, *, retries=8, sleep=time.sleep,
                 persist_response: Callable | None = None):
        self.original, self.ledger, self.retries, self.sleep = original, ledger, retries, sleep
        self.persist_response = persist_response

    def __call__(self, *args, **kwargs):
        messages = kwargs.get("messages")
        role = request_role(messages)
        # Keys/base URLs are neither persisted nor hashed. Deployment identity
        # is bound separately by the exact authorization/runtime receipt.
        public_identity = {k: v for k, v in kwargs.items() if k not in {"api_key", "api_base", "base_url"}}
        try:
            identity = hashlib.sha256(canonical(public_identity)).hexdigest()
        except (TypeError, ValueError) as exc:
            raise OperationalHalt("UNHASHABLE_PROVIDER_REQUEST") from exc
        for attempt in range(self.retries + 1):
            self.ledger.reserve_physical(role, identity)
            try:
                options = dict(kwargs)
                if self.ledger.wall_deadline is not None:
                    remaining = max(0.001, self.ledger.wall_deadline - time.monotonic())
                    options["timeout"] = min(float(options.get("timeout", 120)), remaining)
                response = self.original(*args, **options)
            except Exception as exc:
                with self.ledger._lock:
                    self.ledger.unknown_failed_usage += 1
                retry = transient(exc) and attempt < self.retries
                self.ledger.event("transport_failure", role=role, category=type(exc).__name__, retry=retry,
                                  token_usage="unknown")
                if not retry:
                    raise OperationalHalt("PROVIDER_FAILURE:" + type(exc).__name__) from None
                delay = min(60, 2 ** attempt)
                if self.ledger.wall_deadline is not None:
                    delay = min(delay, max(0, self.ledger.wall_deadline - time.monotonic()))
                self.sleep(delay)
                continue
            # Persist successful paid bodies BEFORE domain parsing/scoring. The
            # private body store is not a new cache or semantic retry policy.
            try:
                if self.persist_response:
                    self.persist_response(identity, response)
                self.ledger.record_response(role, response)
            except Exception:
                raise OperationalHalt("PAID_RESPONSE_PERSISTENCE_FAILED") from None
            return response
        raise AssertionError("unreachable")


def install_transport(litellm, ledger: Ledger, response_directory: Path):
    original = litellm.completion
    response_directory.mkdir()
    counter = [0]
    lock = threading.Lock()
    def persist(identity, response):
        with lock:
            counter[0] += 1
            ordinal = counter[0]
        value = response.model_dump(mode="json")
        path = response_directory / f"{ordinal:07d}_{identity}.json"
        temporary = path.with_suffix(".partial")
        with temporary.open("xb") as stream:
            stream.write(canonical(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    litellm.completion = Transport(original, ledger, persist_response=persist)
    return original


def install_logical_meter(program_class, ledger: Ledger):
    """Reserve before the root program runs; keep all predictor names unchanged.

    A context-local depth prevents nested calls to the same root class being
    counted as new examples. The original __call__ body is always delegated to.
    """
    inherited = "__call__" not in program_class.__dict__
    original = program_class.__call__
    depth = ContextVar("paper_root_call_depth", default=0)
    def measured(self, *args, **kwargs):
        if depth.get():
            return original(self, *args, **kwargs)
        ledger.reserve_logical()
        token = depth.set(1)
        try:
            return original(self, *args, **kwargs)
        finally:
            depth.reset(token)
    program_class.__call__ = measured
    def restore():
        if inherited:
            delattr(program_class, "__call__")
        else:
            program_class.__call__ = original
    return restore
