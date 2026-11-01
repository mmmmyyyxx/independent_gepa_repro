"""Bounded HTTP diagnostics and status-based recovery; no model-output retries."""
from __future__ import annotations

from datetime import timezone
from email.utils import parsedate_to_datetime
import errno
import hashlib
import json
import math
import os
import re
import ssl
import socket
import time

from .data import canonical

RECOVERY_ID = "paper_provider_http_recovery_v2"
HTTP_RETRY_STATUSES = (408, 409, 429)
NETWORK_ERRNOS = {errno.ETIMEDOUT, errno.ECONNRESET, errno.ECONNABORTED, errno.ECONNREFUSED,
                  errno.ENETDOWN, errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EPIPE,
                  10050,10051,10052,10053,10054,10060,10061,10065}
NETWORK_NAMES = {"Timeout", "ReadTimeout", "ConnectTimeout", "WriteTimeout", "PoolTimeout",
                 "APITimeoutError", "APIConnectionError", "ConnectError", "ConnectionError",
                 "ReadError", "WriteError", "RemoteProtocolError", "ProxyError",
                 "ChunkedEncodingError", "IncompleteRead", "RemoteDisconnected"}
SECRET_KEYS = {"authorization", "proxy-authorization", "api_key", "apikey", "access_token",
               "refresh_token", "password", "secret", "cookie", "set-cookie"}


def recovery_policy() -> dict:
    return {"identity": RECOVERY_ID, "max_retries": 8,
            "retry_http_statuses": list(HTTP_RETRY_STATUSES), "retry_all_5xx": True,
            "http_status_precedence": "outer response, outer exception, then causal chain",
            "unknown_or_request_4xx": "diagnostic halt; no message-based retry inference",
            "retry_after": "numeric seconds, HTTP date, or retry-after-ms; never retry before server delay",
            "backoff_seconds": "max(min(60, 2**attempt), valid Retry-After); phase deadline bounds wait",
            "error_evidence": "atomic redacted private record before retry/halt; categories and hashes in ledger",
            "fatal_dispatch": "block new paid calls; cancel queued futures; persist all in-flight responses",
            "changed_request_or_model_fallback": False}


def _get(obj, name, default=None):
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def _status(value):
    if type(value) is int and 100 <= value <= 599:
        return value
    if isinstance(value, str) and re.fullmatch(r"[1-5][0-9]{2}", value.strip()):
        return int(value)
    return None


def _identifier(value):
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:\-\[\]]{1,128}", value) else None


def retry_after(headers, now=None) -> float:
    values = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    delays = []
    for name, multiplier in (("retry-after", 1.), ("retry-after-ms", .001), ("x-ms-retry-after-ms", .001)):
        value = values.get(name)
        if value is None:
            continue
        try:
            number = float(value) * multiplier
            if math.isfinite(number) and number >= 0:
                delays.append(number)
            continue
        except (ValueError, OverflowError):
            pass
        if name == "retry-after":
            try:
                parsed = parsedate_to_datetime(value)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                delays.append(max(0., parsed.timestamp() - (time.time() if now is None else now)))
            except (ValueError, TypeError, OverflowError):
                pass
    return max(delays, default=0.)


def describe(exc: BaseException) -> dict:
    """Recover HTTP metadata across wrappers, without trusting error prose."""
    chain = []
    seen = set()
    current = exc
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        chain.append(current)
        current = _get(current, "__cause__") or _get(current, "__context__")
    status = None
    origin = None
    headers = {}
    response = None
    selected = exc
    for depth, error in enumerate(chain):
        candidate = _get(error, "response")
        observed = _status(_get(candidate, "status_code"))
        source = "response"
        if observed is None:
            observed = _status(_get(error, "status_code"))
            source = "exception"
        if observed is not None:
            status, origin, response, selected = observed, f"chain[{depth}].{source}", candidate, error
            headers = _get(candidate, "headers") or _get(error, "headers") or {}
            break
    if response is None:
        response = next((_get(e, "response") for e in chain if _get(e, "response") is not None), None)
    body = _get(selected, "body")
    if body is None:
        body = next((_get(e, "body") for e in chain if _get(e, "body") is not None), None)
    text = _get(response, "text", "")
    if not isinstance(text, str):
        text = ""
    if body is None and text:
        try:
            body = json.loads(text[:65536])
        except (ValueError, TypeError):
            body = text[:8192]
    if isinstance(body, str):
        try:
            body = json.loads(body[:65536])
        except (ValueError, TypeError):
            pass
    error_body = body.get("error", body) if isinstance(body, dict) else {}
    if not isinstance(error_body, dict):
        error_body = {}
    names = {cls.__name__ for e in chain for cls in type(e).__mro__}
    certificate_failure = any(isinstance(e, ssl.SSLCertVerificationError) or
                              "CERTIFICATE_VERIFY_FAILED" in str(e) for e in chain)
    if status is not None:
        recoverable = status in HTTP_RETRY_STATUSES or 500 <= status <= 599
        category = "http_transient" if recoverable else "http_request_or_access_error"
    elif certificate_failure:
        recoverable, category = False, "certificate_validation_error"
    elif (any(isinstance(e, (TimeoutError, ConnectionError, socket.gaierror, ssl.SSLEOFError)) or
                  isinstance(e, OSError) and (_get(e, "errno") in NETWORK_ERRNOS or
                                             _get(e, "winerror") in NETWORK_ERRNOS) for e in chain)
          or names & NETWORK_NAMES):
        recoverable, category = True, "network_transient"
    else:
        recoverable, category = False, "unclassified_error"
    return {"http_status": status, "status_source": origin, "category": category,
            "recoverable": recoverable, "retry_after_seconds": retry_after(headers),
            "exception_class": type(exc).__name__,
            "error_code": _identifier(error_body.get("code")),
            "error_type": _identifier(error_body.get("type")),
            "error_param": _identifier(error_body.get("param")),
            "request_id_sha256": _request_id_hash(headers, selected),
            "body": body, "response_text": text[:8192],
            "exception_chain": [{"category": type(e).__name__, "message": str(e)[:16384]} for e in chain]}


def _request_id_hash(headers, error):
    lowered = {str(k).lower(): str(v) for k, v in headers.items()}
    value = next((lowered[k] for k in ("x-request-id", "request-id", "x-openai-request-id", "x-trace-id")
                  if lowered.get(k)), None) or _get(error, "request_id")
    return hashlib.sha256(str(value).encode()).hexdigest() if value else None


def public_details(details: dict) -> dict:
    """Strict metadata projection; no raw body, message, request ID or header."""
    keys = ("http_status", "status_source", "category", "recoverable", "retry_after_seconds",
            "exception_class", "error_code", "error_type", "error_param", "request_id_sha256")
    return {("recovery_category" if k == "category" else k): details[k] for k in keys}


def private_record(details: dict, kwargs: dict, *, ordinal: int, identity: str, role: str) -> dict:
    secrets = [str(v) for k, v in kwargs.items() if k.lower() in SECRET_KEYS and v]
    secrets += [v for k, v in os.environ.items() if v and any(s in k.upper() for s in
                ("API_KEY", "ACCESS_TOKEN", "PASSWORD", "SECRET", "AUTHORIZATION"))]
    def scrub(value, depth=0):
        if depth > 8:
            return "[DEPTH_LIMIT]"
        if isinstance(value, dict):
            return {str(k)[:128]: "[REDACTED]" if str(k).lower() in SECRET_KEYS else scrub(v, depth+1)
                    for k, v in list(value.items())[:128]}
        if isinstance(value, (list, tuple)):
            return [scrub(v, depth+1) for v in value[:64]]
        if isinstance(value, str):
            value = value[:65536]
            for secret in sorted(set(secrets), key=len, reverse=True):
                value = value.replace(secret, "[REDACTED]")
            value = re.sub(r"https?://[^\s\"'<>]+", "[URL_REDACTED]", value)
            value = re.sub(r"(?i)\bBearer\s+[^\s\"',<>]+", "Bearer [REDACTED]", value)
            value = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[KEY_REDACTED]", value)
            return value[:8192]
        if value is None or type(value) in (int, float, bool):
            return value
        return {"python_type": type(value).__name__}
    # Body/error prose stays in ignored private evidence. Request shape records
    # model/format/size, never replays a failed prompt into optimization.
    messages = kwargs.get("messages") or []
    shape = {"argument_names": sorted(k for k in kwargs if k.lower() not in SECRET_KEYS),
             "model": kwargs.get("model"), "temperature": kwargs.get("temperature"),
             "max_tokens": kwargs.get("max_tokens"),
             "message_roles": [x.get("role") for x in messages if isinstance(x, dict)],
             "message_characters": [len(str(x.get("content", ""))) for x in messages if isinstance(x, dict)],
             "response_format": kwargs.get("response_format")}
    return scrub({"schema": "paper_provider_error_private_v2", "physical_ordinal": ordinal,
                  "request_sha256": identity, "role": role, "details": details, "request_shape": shape})
