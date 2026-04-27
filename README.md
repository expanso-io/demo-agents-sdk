# demo-agents-sdk

Reference demo: **calling cloud LLM SDKs from inside an Expanso Edge pipeline.**

Each provider (OpenAI, Anthropic, Gemini) is shown two ways:

1. **HTTP-direct** — the pipeline YAML calls the provider's REST endpoint via Expanso's `http` processor. No code, no extra container, no Python. Limited to whatever you can express in Bloblang (no SDK retry/backoff, no typed responses, no tool use).
2. **SDK via subprocess** — the pipeline runs a tiny Python script under Expanso's `subprocess` processor. The script imports the official SDK (`openai`, `anthropic`, `google-genai`) once at startup, then loops on stdin per message. You get the SDK's batteries — retries, structured output, streaming, tool use — without leaving the pipeline.

The shared task across all six pipelines is **support-ticket classification**:

```
input:  {"id": "T-001", "message": "I was charged twice for my subscription"}
output: {"id": "T-001", "category": "billing", "sentiment": "neg", "priority": "high",
         "_provider": "openai", "_mode": "subprocess"}
```

Every pipeline reads the same `data/events.jsonl`, hits its provider, and writes the classified event to stdout.

## Layout

```
demo-agents-sdk/
├── Dockerfile                       # expanso-edge + uv (for SDK-mode pipelines)
├── data/events.jsonl                # 8 sample tickets
├── scripts/
│   ├── openai_classify.py           # PEP 723: deps inline, runs via `uv run -s`
│   ├── anthropic_classify.py
│   └── gemini_classify.py
└── pipelines/
    ├── openai-http.yaml             # http processor → api.openai.com
    ├── openai-sdk.yaml              # subprocess → uv run -s openai_classify.py
    ├── anthropic-http.yaml          # http processor → api.anthropic.com
    ├── anthropic-sdk.yaml           # subprocess → anthropic_classify.py
    ├── gemini-http.yaml             # http processor → generativelanguage.googleapis.com
    └── gemini-sdk.yaml              # subprocess → gemini_classify.py
```

## Quickstart

```bash
# 1. Set keys
cp .env.example .env
# edit .env with real OPENAI_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY

# 2. Validate every pipeline (offline, no API calls)
for f in pipelines/*.yaml; do expanso-cli job validate --offline "$f"; done

# 3. Run an HTTP-direct demo (no build needed, uses stock expanso-edge image)
docker compose run --rm openai-http

# 4. Run an SDK-mode demo (first run builds the runner image, ~2 min)
docker compose run --rm openai-sdk

# 5. Tear down
docker compose down -v
```

## How the two modes compare

| Concern               | HTTP-direct                       | SDK via subprocess                   |
|-----------------------|-----------------------------------|--------------------------------------|
| Lines of code         | 0 (YAML only)                     | ~50 in one Python file               |
| Retry / backoff       | manual (`retries:` field)         | SDK default (exponential, jitter)    |
| Structured output     | provider-specific YAML knobs      | SDK pydantic / typed responses       |
| Tool use, streaming   | hard / not really                 | first-class SDK features             |
| Auth refresh          | static header                     | SDK handles ADC, OAuth, etc.         |
| What runs             | just expanso-edge                 | expanso-edge + Python child process  |
| Cold start            | none                              | once per pipeline run (uv warms cache) |
| Concurrency           | per-message HTTP                  | one message at a time per subprocess |

The pipeline YAML is *radically* simpler in SDK mode — `pipelines/openai-sdk.yaml` is 16 lines vs 50 for `openai-http.yaml`. All the provider-specific complexity moves into `scripts/openai_classify.py`, which gets to use the SDK's idioms instead of fighting Bloblang.

## How `subprocess` works under the hood

The Expanso `subprocess` processor spawns the command once and keeps it alive for the lifetime of the pipeline. Each message is written to the process's stdin (with a trailing newline by default), and the next line on stdout becomes the new message body. Two consequences worth knowing:

1. **You must `flush=True` after every line.** Without it, Python buffers stdout and the pipeline hangs waiting for output. Every script in `scripts/` does this.
2. **Errors stay inside the process.** The scripts catch exceptions and emit `{"error": "..."}` rows so a single bad message doesn't kill the subprocess (which would force Expanso to restart it from scratch).

## Deploying to production via Expanso Cloud

Local Docker Compose is for fast iteration. The production path is **Expanso Cloud → edge nodes**:

1. Push this repo to a Git remote your Expanso Cloud workspace can read.
2. In [cloud.expanso.io](https://cloud.expanso.io), register the pipeline YAMLs from `pipelines/` as jobs.
3. Set the API key secrets (`OPENAI_API_KEY`, etc.) in the workspace's secret store, not in the YAML.
4. Deploy each job to the target edge node group. The cloud orchestrator pushes the pipeline; edge nodes execute it.
5. SDK-mode pipelines need `uv` and the script files on the edge node. Either bake them into a custom edge image (see `Dockerfile`) or mount them via your edge node bootstrap.

The HTTP-direct pipelines have zero infra dependencies — they're pure pipeline definitions. The SDK-mode pipelines trade that simplicity for SDK ergonomics; pick per use-case.

## Models used

- OpenAI: `gpt-4o-mini`
- Anthropic: `claude-haiku-4-5-20251001`
- Gemini: `gemini-2.0-flash`

Override with `OPENAI_MODEL`, `ANTHROPIC_MODEL`, `GEMINI_MODEL` in `.env`.
