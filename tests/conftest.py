"""
Shared pytest fixtures.

The core idea: never call the real Gemini API in tests. We inject a
FakeLLMClient that returns canned, deterministic JSON strings so every test
run is fast, free, and reproducible - exactly the "mocking LLM responses for
deterministic tests" strategy from today's material.
"""

import json
import pytest

from agent import TicketClassifierAgent


class FakeLLMClient:
    """
    Deterministic stand-in for GeminiClient.

    - queue_response(text): push a canned raw response to return next
    - queue_exception(exc): push an exception to raise next
    - call_count: how many times .generate() was invoked (useful for
      asserting retry behaviour)
    """

    def __init__(self):
        self._queue = []
        self.call_count = 0
        self.last_prompt = None

    def queue_response(self, text: str):
        self._queue.append(("response", text))
        return self

    def queue_exception(self, exc: Exception):
        self._queue.append(("exception", exc))
        return self

    def generate(self, prompt: str) -> str:
        self.call_count += 1
        self.last_prompt = prompt
        if not self._queue:
            raise AssertionError("FakeLLMClient.generate() called with no queued response")
        kind, payload = self._queue.pop(0)
        if kind == "exception":
            raise payload
        return payload


def make_json_response(category="Network", priority="High", suggested_action="Check connectivity"):
    return json.dumps(
        {"category": category, "priority": priority, "suggested_action": suggested_action}
    )


@pytest.fixture
def fake_llm_client():
    return FakeLLMClient()


@pytest.fixture
def agent(fake_llm_client):
    return TicketClassifierAgent(llm_client=fake_llm_client)
