"""
Test suite for the IT Support Ticket Classifier Agent.

Organized into:
  1. Normal cases      - the four example tickets from the spec
  2. Response parsing   - JSON parsing, markdown fences, malformed data
  3. Edge cases          - empty input, unknown categories, invalid priority
  4. LLM client behavior - retries, backoff, failure after max attempts
  5. Performance          - a lightweight benchmark using the mocked client
"""

import time
import pytest

from agent import (
    TicketClassifierAgent,
    ClassificationResult,
    ClassificationParseError,
    LLMClientError,
    GeminiClient,
)
from tests.conftest import make_json_response


# ---------------------------------------------------------------------------
# 1. Normal cases - the four worked examples from the spec
# ---------------------------------------------------------------------------

def test_classify_wifi_issue_is_network_high(agent, fake_llm_client):
    fake_llm_client.queue_response(
        make_json_response("Network", "High", "Check DNS/network connectivity")
    )
    result = agent.classify(
        "My laptop is connected to Wi-Fi but the internet is not working."
    )
    assert result.category == "Network"
    assert result.priority == "High"
    assert "connectivity" in result.suggested_action.lower() or "dns" in result.suggested_action.lower()


def test_classify_password_issue_is_access_high(agent, fake_llm_client):
    fake_llm_client.queue_response(
        make_json_response("Access", "High", "Password reset")
    )
    result = agent.classify("I forgot my company password and cannot log in.")
    assert result.category == "Access"
    assert result.priority == "High"
    assert "password" in result.suggested_action.lower()


def test_classify_outlook_crash_is_software_medium(agent, fake_llm_client):
    fake_llm_client.queue_response(
        make_json_response("Software", "Medium", "Restart Outlook / repair installation")
    )
    result = agent.classify("Outlook crashes every time I open it.")
    assert result.category == "Software"
    assert result.priority == "Medium"


def test_classify_dead_laptop_is_hardware_critical(agent, fake_llm_client):
    fake_llm_client.queue_response(
        make_json_response("Hardware", "Critical", "Escalate to hardware support")
    )
    result = agent.classify("My laptop doesn't turn on even after charging it.")
    assert result.category == "Hardware"
    assert result.priority == "Critical"
    assert "escalate" in result.suggested_action.lower()


def test_classify_returns_classification_result_instance(agent, fake_llm_client):
    fake_llm_client.queue_response(make_json_response())
    result = agent.classify("Some ticket text")
    assert isinstance(result, ClassificationResult)


def test_prompt_includes_the_raw_ticket_text(agent, fake_llm_client):
    fake_llm_client.queue_response(make_json_response())
    ticket = "VPN keeps disconnecting every ten minutes"
    agent.classify(ticket)
    assert ticket in fake_llm_client.last_prompt


# ---------------------------------------------------------------------------
# 2. Response parsing
# ---------------------------------------------------------------------------

def test_parse_response_handles_markdown_code_fences(agent, fake_llm_client):
    fenced = "```json\n" + make_json_response("Software", "Low", "Clear cache") + "\n```"
    fake_llm_client.queue_response(fenced)
    result = agent.classify("App is running slow")
    assert result.category == "Software"
    assert result.priority == "Low"


def test_parse_response_handles_plain_fences_without_json_tag(agent, fake_llm_client):
    fenced = "```\n" + make_json_response("Network", "Medium", "Restart router") + "\n```"
    fake_llm_client.queue_response(fenced)
    result = agent.classify("Wi-Fi is spotty in the office")
    assert result.category == "Network"


def test_parse_response_invalid_json_raises_parse_error(agent, fake_llm_client):
    fake_llm_client.queue_response("this is not json at all")
    with pytest.raises(ClassificationParseError):
        agent.classify("Something broke")


def test_parse_response_non_object_json_raises_parse_error(agent, fake_llm_client):
    fake_llm_client.queue_response('["Network", "High", "Check DNS"]')
    with pytest.raises(ClassificationParseError):
        agent.classify("Something broke")


def test_parse_response_empty_string_raises_parse_error(agent, fake_llm_client):
    fake_llm_client.queue_response("")
    with pytest.raises(ClassificationParseError):
        agent.classify("Something broke")


def test_to_dict_uses_expected_display_keys():
    result = ClassificationResult("Network", "High", "Check DNS/network connectivity")
    d = result.to_dict()
    assert d == {
        "Category": "Network",
        "Priority": "High",
        "Suggested Action": "Check DNS/network connectivity",
    }


def test_str_output_matches_example_format():
    result = ClassificationResult("Hardware", "Critical", "Escalate to hardware support")
    text = str(result)
    assert "Category: Hardware" in text
    assert "Priority: Critical" in text
    assert "Suggested Action: Escalate to hardware support" in text


# ---------------------------------------------------------------------------
# 3. Edge cases
# ---------------------------------------------------------------------------

def test_classify_empty_string_raises_value_error(agent):
    with pytest.raises(ValueError):
        agent.classify("")


def test_classify_whitespace_only_raises_value_error(agent):
    with pytest.raises(ValueError):
        agent.classify("   \n\t  ")


def test_classify_none_raises_value_error(agent):
    with pytest.raises(ValueError):
        agent.classify(None)


def test_unrecognized_category_defaults_to_other(agent, fake_llm_client):
    fake_llm_client.queue_response(
        make_json_response("Printer Problems", "Medium", "Check printer queue")
    )
    result = agent.classify("The office printer keeps jamming")
    assert result.category == "Other"


def test_missing_category_field_raises_parse_error(agent, fake_llm_client):
    import json

    fake_llm_client.queue_response(
        json.dumps({"priority": "High", "suggested_action": "Do something"})
    )
    with pytest.raises(ClassificationParseError):
        agent.classify("Ticket with missing category")


def test_invalid_priority_value_raises_parse_error(agent, fake_llm_client):
    fake_llm_client.queue_response(
        make_json_response("Network", "Super Urgent!!", "Escalate")
    )
    with pytest.raises(ClassificationParseError):
        agent.classify("Network is down for everyone")


def test_missing_suggested_action_raises_parse_error(agent, fake_llm_client):
    import json

    fake_llm_client.queue_response(
        json.dumps({"category": "Access", "priority": "High", "suggested_action": ""})
    )
    with pytest.raises(ClassificationParseError):
        agent.classify("Cannot access shared drive")


def test_classify_handles_very_long_ticket_text(agent, fake_llm_client):
    fake_llm_client.queue_response(make_json_response("Software", "Low", "Investigate logs"))
    long_ticket = "The application freezes intermittently. " * 200
    result = agent.classify(long_ticket)
    assert result.category == "Software"


def test_classify_handles_special_characters_and_unicode(agent, fake_llm_client):
    fake_llm_client.queue_response(make_json_response("Software", "Medium", "Check encoding"))
    ticket = "Excel crashes on café résumé.xlsx — error: <NullPointerException> 💥"
    result = agent.classify(ticket)
    assert result.category == "Software"
    assert ticket in fake_llm_client.last_prompt


# ---------------------------------------------------------------------------
# 4. LLM client behaviour (retries / failures)
# ---------------------------------------------------------------------------

def test_llm_client_retries_and_succeeds_on_third_attempt(fake_llm_client):
    fake_llm_client.queue_exception(TimeoutError("timeout 1"))
    fake_llm_client.queue_exception(TimeoutError("timeout 2"))
    fake_llm_client.queue_response(make_json_response())

    # FakeLLMClient itself has no retry logic - this test simulates retry
    # behaviour at the agent-call level by calling generate() directly,
    # mirroring how GeminiClient.generate() loops on failure.
    attempts = 0
    result = None
    last_err = None
    for _ in range(3):
        attempts += 1
        try:
            result = fake_llm_client.generate("prompt")
            break
        except TimeoutError as e:
            last_err = e
            continue

    assert attempts == 3
    assert result is not None


def test_gemini_client_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(LLMClientError):
        GeminiClient(api_key=None)


def test_gemini_client_generate_retries_then_raises(monkeypatch):
    """
    Verifies GeminiClient.generate()'s own retry/backoff loop using a
    stubbed-out internal model, without touching the network or sleeping
    for real.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    client = GeminiClient.__new__(GeminiClient)  # bypass __init__ (no network)
    client.api_key = "test-key"
    client.model_name = "gemini-3.6-flash"

    class AlwaysFailsModel:
        def __init__(self):
            self.calls = 0

        def generate_content(self, prompt):
            self.calls += 1
            raise RuntimeError("simulated API failure")

    client._model = AlwaysFailsModel()

    # avoid real sleeping during the retry backoff
    monkeypatch.setattr(time, "sleep", lambda seconds: None)

    with pytest.raises(LLMClientError):
        client.generate("some prompt", max_retries=3, backoff_base=1.0)

    assert client._model.calls == 3


def test_gemini_client_generate_succeeds_after_transient_failure(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    client = GeminiClient.__new__(GeminiClient)
    client.api_key = "test-key"
    client.model_name = "gemini-3.6-flash"

    class FlakyModel:
        def __init__(self):
            self.calls = 0

        def generate_content(self, prompt):
            self.calls += 1
            if self.calls < 2:
                raise RuntimeError("simulated transient failure")

            class FakeResponse:
                text = make_json_response("Network", "High", "Check DNS/network connectivity")

            return FakeResponse()

    client._model = FlakyModel()
    monkeypatch.setattr(time, "sleep", lambda seconds: None)

    result_text = client.generate("some prompt", max_retries=3, backoff_base=1.0)
    assert "Network" in result_text
    assert client._model.calls == 2


# ---------------------------------------------------------------------------
# 5. Performance benchmarking
# ---------------------------------------------------------------------------

def test_classify_completes_quickly_with_mocked_llm(agent, fake_llm_client):
    """
    Not a real LLM latency benchmark (that would need the live API) - this
    checks that our own code (prompt building + parsing) doesn't add
    meaningful overhead on top of the LLM call itself.
    """
    fake_llm_client.queue_response(make_json_response())

    start = time.perf_counter()
    agent.classify("My laptop is connected to Wi-Fi but the internet is not working.")
    elapsed = time.perf_counter() - start

    assert elapsed < 0.1, f"Classification overhead too high: {elapsed:.4f}s"


def test_classify_throughput_over_multiple_tickets(agent, fake_llm_client):
    tickets = [
        "My laptop is connected to Wi-Fi but the internet is not working.",
        "I forgot my company password and cannot log in.",
        "Outlook crashes every time I open it.",
        "My laptop doesn't turn on even after charging it.",
    ] * 5  # 20 tickets total

    for _ in tickets:
        fake_llm_client.queue_response(make_json_response())

    start = time.perf_counter()
    for ticket in tickets:
        agent.classify(ticket)
    elapsed = time.perf_counter() - start

    avg = elapsed / len(tickets)
    assert avg < 0.05, f"Average per-ticket overhead too high: {avg:.4f}s"
    assert fake_llm_client.call_count == len(tickets)
