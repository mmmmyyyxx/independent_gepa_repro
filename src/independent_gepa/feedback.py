"""Reflection payload isolation and recursive leakage checks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .protocol import ProtocolViolation

FORBIDDEN_KEY_FRAGMENTS = (
    "peer",
    "team",
    "vote",
    "responsibility",
    "coalition",
    "active_lane",
    "same_wrong",
    "member_gain",
    "pivotal",
    "gold_vote",
    "plurality_margin",
)
FORBIDDEN_EXACT_KEYS = {"g", "h", "m"}


def assert_feedback_isolation(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).lower()
            if key in FORBIDDEN_EXACT_KEYS or any(fragment in key for fragment in FORBIDDEN_KEY_FRAGMENTS):
                raise ProtocolViolation(f"forbidden team/peer feedback field at {path}.{raw_key}")
            assert_feedback_isolation(child, path=f"{path}.{raw_key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, child in enumerate(value):
            assert_feedback_isolation(child, path=f"{path}[{index}]")
