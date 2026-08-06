"""Deterministic fake transports used only by offline tests and smoke commands."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

from .provider import ProviderResponse

_GOLD_MARKER = re.compile(r"\[gold=([A-Z])\]", re.IGNORECASE)


class DeterministicFakeTransport:
    def __init__(self) -> None:
        self.requests: list[Mapping[str, Any]] = []

    def __call__(self, request: Mapping[str, Any]) -> ProviderResponse:
        self.requests.append(request)
        messages = request["messages"]
        if len(messages) == 1:
            text = "Return only one unambiguous final answer in the required option-letter format."
        else:
            system_text = str(messages[0]["content"])
            user_text = str(messages[-1]["content"])
            marker = _GOLD_MARKER.search(user_text)
            if marker:
                gold = marker.group(1).upper()
                answer = gold if "unambiguous" in system_text.lower() else chr(
                    ord("A") + (ord(gold) - ord("A") + 1) % 3
                )
            else:
                answer = chr(ord("A") + hashlib.sha256(user_text.encode("utf-8")).digest()[0] % 3)
            text = f"Final answer: {answer}"
        prompt_tokens = sum(max(1, len(str(message["content"]).split())) for message in messages)
        return ProviderResponse(
            text=text,
            finish_reason="stop",
            prompt_tokens=prompt_tokens,
            completion_tokens=max(1, len(text.split())),
            request_id=f"fake-{len(self.requests)}",
        )
