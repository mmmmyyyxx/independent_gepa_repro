"""OpenAI-compatible provider with exact-request caching and role accounting."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from .bundle import canonical_json
from .protocol import BudgetExceeded, OperationalFailure, ProtocolViolation

TRANSIENT_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    finish_reason: str | None
    prompt_tokens: int
    completion_tokens: int
    request_id: str | None = None

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class CompletionTransport(Protocol):
    def __call__(self, request: Mapping[str, Any]) -> ProviderResponse: ...


class ProviderHTTPError(RuntimeError):
    def __init__(self, status_code: int, message: str = "provider HTTP error"):
        super().__init__(message)
        self.status_code = int(status_code)


@dataclass
class RoleUsage:
    logical_calls: int = 0
    real_requests: int = 0
    cache_hits: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost: float = 0.0
    cost_available: bool = False

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class ProviderAccounting:
    roles: dict[str, RoleUsage] = field(
        default_factory=lambda: {"task": RoleUsage(), "reflection": RoleUsage()}
    )
    state_path: Path | None = None
    identity: str | None = None
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.state_path is None or not self.state_path.exists():
            return
        try:
            row = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProtocolViolation(f"invalid persisted provider accounting: {exc}") from exc
        if not isinstance(row, dict) or row.get("schema_version") != 1:
            raise ProtocolViolation("persisted provider accounting schema mismatch")
        if row.get("identity") != self.identity:
            raise ProtocolViolation("persisted provider accounting identity mismatch")
        raw_roles = row.get("roles")
        if not isinstance(raw_roles, dict) or set(raw_roles) != {"task", "reflection"}:
            raise ProtocolViolation("persisted provider accounting roles mismatch")
        restored: dict[str, RoleUsage] = {}
        for name, value in raw_roles.items():
            if not isinstance(value, dict):
                raise ProtocolViolation("persisted provider accounting role is invalid")
            restored[name] = RoleUsage(
                logical_calls=int(value.get("logical_calls", 0)),
                real_requests=int(value.get("real_requests", 0)),
                cache_hits=int(value.get("cache_hits", 0)),
                prompt_tokens=int(value.get("prompt_tokens", 0)),
                completion_tokens=int(value.get("completion_tokens", 0)),
                estimated_cost=float(value.get("estimated_cost", 0.0)),
                cost_available=bool(value.get("cost_available", False)),
            )
            if min(
                restored[name].logical_calls,
                restored[name].real_requests,
                restored[name].cache_hits,
                restored[name].prompt_tokens,
                restored[name].completion_tokens,
            ) < 0:
                raise ProtocolViolation("persisted provider accounting contains a negative value")
        self.roles = restored

    def _persist_locked(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "schema_version": 1,
            "identity": self.identity,
            "roles": {
                name: {
                    "logical_calls": value.logical_calls,
                    "real_requests": value.real_requests,
                    "cache_hits": value.cache_hits,
                    "prompt_tokens": value.prompt_tokens,
                    "completion_tokens": value.completion_tokens,
                    "estimated_cost": value.estimated_cost,
                    "cost_available": value.cost_available,
                }
                for name, value in sorted(self.roles.items())
            },
        }
        payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        temporary = self.state_path.with_name(
            f".{self.state_path.name}.{threading.get_ident()}.{time.time_ns()}.tmp"
        )
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        try:
            for attempt in range(5):
                try:
                    os.replace(temporary, self.state_path)
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.02 * (attempt + 1))
        finally:
            temporary.unlink(missing_ok=True)

    def role(self, name: str) -> RoleUsage:
        if name not in self.roles:
            raise ProtocolViolation(f"unknown provider role: {name}")
        return self.roles[name]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            role_rows = {
                name: {
                    "logical_calls": value.logical_calls,
                    "real_requests": value.real_requests,
                    "cache_hits": value.cache_hits,
                    "prompt_tokens": value.prompt_tokens,
                    "completion_tokens": value.completion_tokens,
                    "total_tokens": value.total_tokens,
                    "estimated_cost": value.estimated_cost if value.cost_available else None,
                    "cost_status": "estimated" if value.cost_available else "unavailable_missing_pricing",
                }
                for name, value in sorted(self.roles.items())
            }
            all_costs_available = all(value.cost_available for value in self.roles.values())
            return {
                "roles": role_rows,
                "real_requests": sum(value.real_requests for value in self.roles.values()),
                "total_tokens": sum(value.total_tokens for value in self.roles.values()),
                "estimated_cost": (
                    sum(value.estimated_cost for value in self.roles.values())
                    if all_costs_available
                    else None
                ),
                "cost_status": (
                    "estimated" if all_costs_available else "unavailable_missing_bundle_pricing"
                ),
            }


@dataclass(frozen=True)
class TokenBudgetPolicy:
    target_tokens: int
    hard_tokens: int
    stop_reserve_tokens: int

    def __post_init__(self) -> None:
        if not (0 < self.stop_reserve_tokens < self.target_tokens <= self.hard_tokens):
            raise ProtocolViolation("invalid token budget policy")


class ExactRequestCache:
    def __init__(self, path: Path | None = None):
        self.path = path
        self._lock = threading.RLock()
        self._entries: dict[str, dict[str, Any]] = {}
        if path is not None and path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ProtocolViolation(f"invalid exact-request cache: {exc}") from exc
            if not isinstance(loaded, dict):
                raise ProtocolViolation("exact-request cache must be a JSON object")
            self._entries = {str(key): dict(value) for key, value in loaded.items()}

    @staticmethod
    def key(request: Mapping[str, Any]) -> str:
        return hashlib.sha256(canonical_json(request).encode("utf-8")).hexdigest()

    def get(self, request: Mapping[str, Any]) -> ProviderResponse | None:
        with self._lock:
            row = self._entries.get(self.key(request))
        if row is None:
            return None
        return ProviderResponse(
            text=str(row["text"]),
            finish_reason=row.get("finish_reason"),
            prompt_tokens=int(row.get("prompt_tokens", 0)),
            completion_tokens=int(row.get("completion_tokens", 0)),
            request_id=row.get("request_id"),
        )

    def put(self, request: Mapping[str, Any], response: ProviderResponse) -> None:
        with self._lock:
            self._entries[self.key(request)] = {
                "text": response.text,
                "finish_reason": response.finish_reason,
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "request_id": response.request_id,
            }
            if self.path is not None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                payload = json.dumps(self._entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
                temporary = self.path.with_name(
                    f".{self.path.name}.{threading.get_ident()}.{time.time_ns()}.tmp"
                )
                temporary.write_text(payload, encoding="utf-8", newline="\n")
                try:
                    for attempt in range(5):
                        try:
                            os.replace(temporary, self.path)
                            break
                        except PermissionError:
                            if attempt == 4:
                                raise
                            time.sleep(0.02 * (attempt + 1))
                finally:
                    temporary.unlink(missing_ok=True)


class OpenAICompatibleProvider:
    """Provider wrapper. A real transport requires two independent opt-ins."""

    def __init__(
        self,
        *,
        task_model: str,
        reflection_model: str,
        transport: CompletionTransport,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float,
        max_retries: int,
        enable_thinking: bool = False,
        cache: ExactRequestCache | None = None,
        accounting: ProviderAccounting | None = None,
        pricing_per_million_tokens: Mapping[str, Mapping[str, float]] | None = None,
        token_budget_policy: TokenBudgetPolicy | None = None,
    ):
        if enable_thinking is not False:
            raise ProtocolViolation("enable_thinking must be false")
        if not task_model or not reflection_model:
            raise ProtocolViolation("fixed task and reflection model names are required")
        if max_tokens <= 0 or timeout_seconds <= 0 or max_retries < 0:
            raise ProtocolViolation("invalid provider token, timeout, or retry configuration")
        self.task_model = task_model
        self.reflection_model = reflection_model
        self.transport = transport
        self.temperature = float(temperature)
        self.max_tokens = int(max_tokens)
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = int(max_retries)
        self.cache = cache or ExactRequestCache()
        self.accounting = accounting or ProviderAccounting()
        self.pricing = {
            str(role): {
                "prompt": float(rates.get("prompt", 0.0)),
                "completion": float(rates.get("completion", 0.0)),
            }
            for role, rates in (pricing_per_million_tokens or {}).items()
        }
        self.token_budget_policy = token_budget_policy
        for role in self.pricing:
            if role in self.accounting.roles:
                self.accounting.roles[role].cost_available = True

    @classmethod
    def from_environment(
        cls,
        *,
        task_model: str,
        reflection_model: str,
        api_key_env: str,
        base_url_env: str,
        config_allows_real_api: bool,
        cli_allows_real_api: bool,
        **kwargs: Any,
    ) -> "OpenAICompatibleProvider":
        if not config_allows_real_api or not cli_allows_real_api:
            raise ProtocolViolation("real API transport requires config and CLI opt-in")
        api_key = os.environ.get(api_key_env)
        base_url = os.environ.get(base_url_env)
        if not api_key or not base_url:
            raise ProtocolViolation("provider credentials or base URL are missing")
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url)

        def transport(request: Mapping[str, Any]) -> ProviderResponse:
            try:
                response = client.chat.completions.create(**dict(request))
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                if isinstance(status_code, int):
                    raise ProviderHTTPError(status_code) from exc
                if isinstance(exc, (TimeoutError, ConnectionError)):
                    raise
                name = type(exc).__name__.lower()
                if "timeout" in name:
                    raise TimeoutError("provider timeout") from exc
                if "connection" in name:
                    raise ConnectionError("provider connection failure") from exc
                raise OperationalFailure(
                    f"non-transient provider failure: {type(exc).__name__}"
                ) from exc
            if not response.choices:
                raise OperationalFailure("provider returned no choices")
            choice = response.choices[0]
            content = choice.message.content
            if not isinstance(content, str):
                raise OperationalFailure("provider returned non-text content")
            usage = response.usage
            return ProviderResponse(
                text=content,
                finish_reason=choice.finish_reason,
                prompt_tokens=int(usage.prompt_tokens if usage else 0),
                completion_tokens=int(usage.completion_tokens if usage else 0),
                request_id=getattr(response, "id", None),
            )

        return cls(
            task_model=task_model,
            reflection_model=reflection_model,
            transport=transport,
            **kwargs,
        )

    def _request(self, role: str, messages: Sequence[Mapping[str, str]]) -> dict[str, Any]:
        model = self.task_model if role == "task" else self.reflection_model
        return {
            "model": model,
            "messages": [dict(message) for message in messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout_seconds,
            "extra_body": {"enable_thinking": False},
        }

    def complete(self, role: str, messages: Sequence[Mapping[str, str]]) -> tuple[ProviderResponse, bool]:
        with self.accounting._lock:
            usage = self.accounting.role(role)
            usage.logical_calls += 1
            self.accounting._persist_locked()
        request = self._request(role, messages)
        cached = self.cache.get(request)
        if cached is not None:
            with self.accounting._lock:
                usage.cache_hits += 1
                self.accounting._persist_locked()
            return cached, True
        if self.token_budget_policy is not None:
            consumed = int(self.accounting.snapshot()["total_tokens"])
            if consumed >= self.token_budget_policy.target_tokens:
                raise BudgetExceeded(
                    f"model token target reached before {role} request: "
                    f"consumed={consumed}, target={self.token_budget_policy.target_tokens}"
                )
        last_error: BaseException | None = None
        for attempt in range(self.max_retries + 1):
            with self.accounting._lock:
                usage.real_requests += 1
                self.accounting._persist_locked()
            try:
                response = self.transport(request)
                if not isinstance(response, ProviderResponse):
                    raise OperationalFailure("transport returned an invalid response schema")
                with self.accounting._lock:
                    usage.prompt_tokens += response.prompt_tokens
                    usage.completion_tokens += response.completion_tokens
                    rates = self.pricing.get(role, {})
                    usage.estimated_cost += (
                        response.prompt_tokens * float(rates.get("prompt", 0.0))
                        + response.completion_tokens * float(rates.get("completion", 0.0))
                    ) / 1_000_000
                    self.accounting._persist_locked()
                self.cache.put(request, response)
                if self.token_budget_policy is not None:
                    consumed = int(self.accounting.snapshot()["total_tokens"])
                    if consumed > self.token_budget_policy.hard_tokens:
                        raise BudgetExceeded(
                            "hard model-token tolerance exceeded: "
                            f"consumed={consumed}, hard={self.token_budget_policy.hard_tokens}"
                        )
                return response, False
            except ProviderHTTPError as exc:
                last_error = exc
                if exc.status_code not in TRANSIENT_STATUS_CODES:
                    break
            except (TimeoutError, ConnectionError) as exc:
                last_error = exc
            except OperationalFailure:
                raise
            except Exception as exc:
                raise OperationalFailure(f"non-transient provider/schema failure: {type(exc).__name__}") from exc
            if attempt < self.max_retries:
                time.sleep(min(0.05 * (2**attempt), 0.2))
        raise OperationalFailure(
            f"provider request failed after transient retry policy: {type(last_error).__name__}"
        ) from last_error

    def reflection_callable(self) -> Callable[[str | list[dict[str, str]]], str]:
        def call(prompt: str | list[dict[str, str]]) -> str:
            messages = (
                [{"role": "user", "content": prompt}]
                if isinstance(prompt, str)
                else [dict(message) for message in prompt]
            )
            response, _ = self.complete("reflection", messages)
            return response.text

        return call

    def __repr__(self) -> str:
        return (
            "OpenAICompatibleProvider("
            f"task_model={self.task_model!r}, reflection_model={self.reflection_model!r}, "
            f"max_retries={self.max_retries})"
        )
