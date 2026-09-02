# IT Support Ticket Classifier Agent

An LLM agent that reads an employee's IT support message and classifies it into:

- **Category** — Network / Access / Software / Hardware / Other
- **Priority** — Low / Medium / High / Critical
- **Suggested Action** — a short, actionable next step

Built with Gemini (`GEMINI_MODEL`, defaults to `gemini-3.6-flash`), a mocked
test suite, a Docker container, and a GitHub Actions CI pipeline.

## Project layout

```
.
├── agent.py                     # Agent, GeminiClient wrapper, prompt, parser, CLI
├── requirements.txt              # Runtime deps
├── requirements-dev.txt          # Runtime + test deps
├── .env.example                  # Copy to .env and fill in your key
├── Dockerfile
├── .dockerignore
├── tests/
│   ├── __init__.py
│   ├── conftest.py               # FakeLLMClient fixture (no real API calls)
│   └── test_agent.py             # 28 tests: normal, edge, retry, perf
└── .github/workflows/ci.yml      # Test -> build Docker image on every push/PR
```
## Project Description

An AI-powered IT Support Ticket Classifier Agent built with Gemini that automatically analyzes employee IT support requests and determines the appropriate category, priority, and suggested next action.

The agent is designed as a production-style LLM application and returns structured results that can be easily consumed by downstream systems such as ticketing or IT service-management platforms.

Example

Input:

My laptop is connected to Wi-Fi but the internet is not working.

'Agent Output:' 

Category: Network
Priority: High
Suggested Action: Check DNS/network connectivity
Key Features
LLM-based classification using Google Gemini
Classifies tickets into:
Network
Access
Software
Hardware
Other
Assigns priority:
Low
Medium
High
Critical