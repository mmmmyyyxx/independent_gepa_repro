"""Leakage audit for public artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .protocol import ProtocolViolation

SENSITIVE_KEY_FRAGMENTS = (
    "prompt_text",
    "system_prompt",
    "question",
    "choices",
    "gold_answer",
    "raw_response",
    "response_text",
    "api_key",
    "base_url",
    "endpoint",
    "cache_content",
)
WINDOWS_ABSOLUTE = re.compile(r"(?i)\b[A-Z]:[\\/][^\s\"']+")
POSIX_ABSOLUTE = re.compile(r"(?<![:\w])/(?:home|Users|root|tmp|var)/[^\s\"']+")
SECRET_VALUE = re.compile(r"(?i)(?:sk-[A-Za-z0-9_-]{12,}|bearer\s+[A-Za-z0-9._-]{12,})")


@dataclass(frozen=True)
class AuditFinding:
    path: str
    reason: str


def _inspect(value: Any, *, path: str, findings: list[AuditFinding]) -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            lowered = key.lower()
            if any(fragment in lowered for fragment in SENSITIVE_KEY_FRAGMENTS):
                findings.append(AuditFinding(f"{path}.{key}", "sensitive key in public artifact"))
            _inspect(child, path=f"{path}.{key}", findings=findings)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, child in enumerate(value):
            _inspect(child, path=f"{path}[{index}]", findings=findings)
    elif isinstance(value, str):
        if WINDOWS_ABSOLUTE.search(value) or POSIX_ABSOLUTE.search(value):
            findings.append(AuditFinding(path, "machine-specific absolute path"))
        if SECRET_VALUE.search(value):
            findings.append(AuditFinding(path, "credential-like value"))


def audit_value(value: Any) -> tuple[AuditFinding, ...]:
    findings: list[AuditFinding] = []
    _inspect(value, path="$", findings=findings)
    return tuple(findings)


def audit_public_paths(paths: Iterable[Path]) -> tuple[AuditFinding, ...]:
    findings: list[AuditFinding] = []
    for path in paths:
        if path.is_dir():
            candidates = sorted(item for item in path.rglob("*") if item.is_file())
        else:
            candidates = [path]
        for candidate in candidates:
            relative = candidate.name
            if candidate.suffix.lower() not in {".json", ".jsonl"}:
                findings.append(AuditFinding(relative, "unsupported public artifact file type"))
                continue
            try:
                if candidate.suffix.lower() == ".jsonl":
                    values = [
                        json.loads(line)
                        for line in candidate.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                    ]
                    value: Any = values
                else:
                    value = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                findings.append(AuditFinding(relative, "invalid public JSON"))
                continue
            for finding in audit_value(value):
                findings.append(AuditFinding(f"{relative}:{finding.path}", finding.reason))
    return tuple(findings)


def require_clean_public_artifacts(paths: Iterable[Path]) -> None:
    findings = audit_public_paths(paths)
    if findings:
        preview = "; ".join(f"{row.path}: {row.reason}" for row in findings[:5])
        raise ProtocolViolation(f"public artifact leakage audit failed: {preview}")
