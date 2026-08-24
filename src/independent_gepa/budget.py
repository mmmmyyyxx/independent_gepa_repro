"""Frozen logical-evaluation budgets and accounting."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from .protocol import BudgetExceeded, ProtocolViolation


@dataclass
class BudgetLedger:
    total_budget: int
    member_count: int = 5
    consumed_by_member: dict[int, int] = field(default_factory=dict)
    state_paths: Mapping[int, Path] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.total_budget < self.member_count or self.member_count <= 0:
            raise ProtocolViolation("total budget must provide a positive equal member allocation")
        restored: dict[int, int] = {}
        for index in range(self.member_count):
            path = self.state_paths.get(index)
            if path is None or not path.exists():
                restored[index] = 0
                continue
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ProtocolViolation(f"invalid persisted budget ledger for member {index}: {exc}") from exc
            expected_identity = {
                "schema_version": 1,
                "total_budget": self.total_budget,
                "member_count": self.member_count,
                "member_id": index,
                "member_budget": self.member_budget,
            }
            if not isinstance(row, dict) or any(row.get(key) != value for key, value in expected_identity.items()):
                raise ProtocolViolation(f"persisted budget identity mismatch for member {index}")
            consumed = row.get("consumed")
            if not isinstance(consumed, int) or consumed < 0 or consumed > self.member_budget:
                raise ProtocolViolation(f"invalid persisted budget consumption for member {index}")
            restored[index] = consumed
        self.consumed_by_member = restored

    @property
    def member_budget(self) -> int:
        return self.total_budget // self.member_count

    @property
    def allocated_total(self) -> int:
        return self.member_budget * self.member_count

    @property
    def unallocated_remainder(self) -> int:
        return self.total_budget - self.allocated_total

    @property
    def consumed_total(self) -> int:
        with self._lock:
            return sum(self.consumed_by_member.values())

    def consume(self, member_id: int, count: int = 1) -> None:
        with self._lock:
            if member_id not in self.consumed_by_member:
                raise ProtocolViolation(f"unknown member_id: {member_id}")
            if count <= 0:
                raise ProtocolViolation("logical evaluation count must be positive")
            proposed = self.consumed_by_member[member_id] + count
            if proposed > self.member_budget:
                raise BudgetExceeded(
                    f"member {member_id} budget overrun: proposed={proposed}, limit={self.member_budget}"
                )
            self.consumed_by_member[member_id] = proposed
            self._persist(member_id)

    def _persist(self, member_id: int) -> None:
        path = self.state_paths.get(member_id)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "schema_version": 1,
            "total_budget": self.total_budget,
            "member_count": self.member_count,
            "member_id": member_id,
            "member_budget": self.member_budget,
            "consumed": self.consumed_by_member[member_id],
        }
        payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        temporary = path.with_name(
            f".{path.name}.{threading.get_ident()}.{time.time_ns()}.tmp"
        )
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        try:
            for attempt in range(5):
                try:
                    os.replace(temporary, path)
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.02 * (attempt + 1))
        finally:
            temporary.unlink(missing_ok=True)

    def can_consume(self, member_id: int, count: int) -> bool:
        with self._lock:
            if member_id not in self.consumed_by_member or count < 0:
                return False
            return self.consumed_by_member[member_id] + count <= self.member_budget

    def remaining(self, member_id: int) -> int:
        with self._lock:
            if member_id not in self.consumed_by_member:
                raise ProtocolViolation(f"unknown member_id: {member_id}")
            return self.member_budget - self.consumed_by_member[member_id]

    def snapshot(self) -> Mapping[str, object]:
        with self._lock:
            return {
                "accounting_unit": "logical_task_example_evaluations",
                "total_cap": self.total_budget,
                "member_cap": self.member_budget,
                "allocated_total": self.allocated_total,
                "unallocated_remainder": self.unallocated_remainder,
                "consumed_total": sum(self.consumed_by_member.values()),
                "consumed_by_member": {
                    str(key): value for key, value in sorted(self.consumed_by_member.items())
                },
            }
