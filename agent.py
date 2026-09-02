"""
IT Support Ticket Classifier Agent
-----------------------------------
Classifies employee IT support tickets into:
  - Category         (Network / Access / Software / Hardware / Other)
  - Priority          (Low / Medium / High / Critical)
  - Suggested Action  (short actionable next step)

The LLM call is isolated behind a small client class (GeminiClient) so that
tests can inject a fake client and get fully deterministic behaviour without
ever hitting the network or needing a real API key.
"""

import os
import re
import sys
import json
import time
import logging
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("ticket_classifier")

VALID_CATEGORIES = {"Network", "Access", "Software", "Hardware", "Other"}
VALID_PRIORITIES = {"Low", "Medium", "High", "Critical"}

PROMPT_TEMPLATE = """You are an IT Support Ticket Classification Agent.

Read the employee's message and classify it. Respond with ONLY valid JSON
(no markdown fences, no commentary) in exactly this shape:

{{
  "category": "Network | Access | Software | Hardware | Other",
  "priority": "Low | Medium | High | Critical",
  "suggested_action": "short actionable next step"
}}

Rules:
- "category" must be exactly one of: Network, Access, Software, Hardware, Other.
- "priority" must be exactly one of: Low, Medium, High, Critical.
- Hardware issues that stop someone from working entirely are usually Critical.
- Login/password/access issues are usually High priority.
- Be concise in "suggested_action" (under 12 words).

Employee ticket:
\"\"\"{ticket_text}\"\"\"
"""


class LLMClientError(Exception):
    """Raised when the underlying LLM call fails irrecoverably."""


class ClassificationParseError(Exception):
    """Raised when the LLM response cannot be parsed into a valid classification."""


@dataclass
class ClassificationResult:
    category: str
    priority: str
    suggested_action: str

    def to_dict(self) -> dict:
        return {
            "Category": self.category,
            "Priority": self.priority,
            "Suggested Action": self.suggested_action,
        }

    def __str__(self) -> str:
        d = self.to_dict()
        return "\n".join(f"{k}: {v}" for k, v in d.items())


class GeminiClient:
    """
    Thin wrapper around the Gemini API.

    Kept deliberately small so it can be swapped for a fake/mock in tests.
    Model name and API key are read from environment variables so the same
    code works across dev / staging / prod with different .env files.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

        if not self.api_key:
            raise LLMClientError(
                "GEMINI_API_KEY is not set. Add it to your .env file "
                "(see .env.example)."
            )

        # Imported lazily so unit tests that never construct a real
        # GeminiClient don't need the google-generativeai package installed.
        import google.generativeai as genai

        genai.configure(api_key=self.api_key)
        self._model = genai.GenerativeModel(self.model_name)

    def generate(self, prompt: str, max_retries: int = 3, backoff_base: float = 2.0) -> str:
        last_error: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                response = self._model.generate_content(prompt)
                return response.text
            except Exception as exc:  # noqa: BLE001 - deliberately broad, re-raised below
                last_error = exc
                logger.warning("LLM call failed (attempt %d/%d): %s", attempt, max_retries, exc)
                if attempt < max_retries:
                    time.sleep(min(backoff_base ** attempt, 10))
        raise LLMClientError(f"LLM call failed after {max_retries} attempts: {last_error}")


class TicketClassifierAgent:
    """
    Orchestrates prompt construction, the LLM call, and response parsing.

    Accepts any object with a `.generate(prompt) -> str` method as the
    llm_client, which is what makes this trivially testable with a fake.
    """

    def __init__(self, llm_client=None):
        self.llm_client = llm_client or GeminiClient()

    def build_prompt(self, ticket_text: str) -> str:
        return PROMPT_TEMPLATE.format(ticket_text=ticket_text.strip())

    def classify(self, ticket_text: str) -> ClassificationResult:
        if ticket_text is None or not ticket_text.strip():
            raise ValueError("ticket_text must be a non-empty string")

        prompt = self.build_prompt(ticket_text)
        raw_response = self.llm_client.generate(prompt)
        return self._parse_response(raw_response)

    @staticmethod
    def _parse_response(raw: str) -> ClassificationResult:
        if raw is None:
            raise ClassificationParseError("LLM returned an empty response")

        cleaned = raw.strip()
        # Strip ```json ... ``` or ``` ... ``` fences if the model added them.
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.MULTILINE).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ClassificationParseError(
                f"Could not parse LLM response as JSON: {raw!r}"
            ) from exc

        if not isinstance(data, dict):
            raise ClassificationParseError(f"Expected a JSON object, got: {raw!r}")

        category = str(data.get("category", "")).strip()
        priority = str(data.get("priority", "")).strip()
        action = str(data.get("suggested_action", "")).strip()

        if not category:
            raise ClassificationParseError("LLM response is missing 'category'")
        if category not in VALID_CATEGORIES:
            logger.warning("Unrecognized category '%s' - defaulting to 'Other'", category)
            category = "Other"

        if priority not in VALID_PRIORITIES:
            raise ClassificationParseError(f"Invalid priority returned: {priority!r}")

        if not action:
            raise ClassificationParseError("LLM response is missing 'suggested_action'")

        return ClassificationResult(category=category, priority=priority, suggested_action=action)


def main() -> None:
    """CLI entrypoint: python agent.py "My laptop won't connect to Wi-Fi" """
    if len(sys.argv) > 1:
        ticket_text = " ".join(sys.argv[1:])
    else:
        ticket_text = sys.stdin.read()

    agent = TicketClassifierAgent()
    result = agent.classify(ticket_text)
    print(result)


if __name__ == "__main__":
    main()
