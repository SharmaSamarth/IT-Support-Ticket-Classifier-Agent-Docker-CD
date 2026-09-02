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

## 1. Local setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements-dev.txt

cp .env.example .env
# then edit .env and set:
#   GEMINI_API_KEY=your_real_key
#   GEMINI_MODEL=gemini-3.6-flash
```

## 2. Run the agent

```bash
python agent.py "My laptop is connected to Wi-Fi but the internet is not working."
```

Expected output shape:

```
Category: Network
Priority: High
Suggested Action: Check DNS/network connectivity
```

## 3. Run the test suite

```bash
pytest tests/ -v --cov=agent --cov-report=term-missing
```

The suite (28 tests, currently 88% coverage of `agent.py`) never calls the
real Gemini API — a `FakeLLMClient` in `tests/conftest.py` returns canned
JSON so results are deterministic and tests run in well under a second.
It covers:

- **Normal cases** — the four worked examples (Wi-Fi, password, Outlook, dead laptop)
- **Response parsing** — markdown-fenced JSON, malformed JSON, non-object JSON
- **Edge cases** — empty/whitespace/None input, unknown category fallback,
  invalid priority, missing fields, very long tickets, unicode/special characters
- **LLM client behaviour** — retry-then-succeed, retry exhaustion/backoff,
  missing API key
- **Performance** — per-call and 20-ticket throughput overhead assertions

## 4. Build and run the Docker container

```bash
docker build -t ticket-classifier-agent .

docker run --rm -it --env-file .env ticket-classifier-agent \
  "I forgot my company password and cannot log in."
```

The image runs as a non-root user, reads config from environment variables
(so the same image works across dev/staging/prod via different `.env`
files or `-e APP_ENV=...`), and includes a `HEALTHCHECK`.

## 5. CI pipeline (GitHub Actions)

`.github/workflows/ci.yml` runs on every push/PR to `main`:

1. **test** job — matrix over Python 3.10 and 3.11, installs deps, runs the
   full pytest suite with coverage (using a dummy `GEMINI_API_KEY` since no
   real network calls happen), uploads the coverage report as an artifact.
2. **docker-build** job — runs only after tests pass, builds the Docker
   image with Buildx/layer caching, and smoke-tests that the image can
   import `agent` cleanly.

To push the image to a registry (e.g. Docker Hub, GHCR) as a next step,
add a login step and set `push: true` with proper tags in the
`docker-build` job — intentionally left out here since it needs registry
credentials as secrets.

## Notes / assumptions

- `GeminiClient.generate()` retries up to 3 times with exponential backoff
  before raising `LLMClientError`.
- The parser strips ```` ```json ... ``` ```` fences in case the model wraps
  its JSON, and falls back category to `"Other"` if the model returns an
  unrecognized category (but still requires a valid priority — an invalid
  priority is treated as a hard parse error since priority drives triage).
- No API key or secret is ever required for tests or CI — that's the point
  of mocking the LLM.
