# demo-agents-sdk

Reference demo: **calling cloud LLM SDKs from inside an Expanso Edge pipeline.**

Each provider (OpenAI, Anthropic, Gemini) is shown two ways:

1. **HTTP-direct** — the pipeline YAML calls the provider's REST endpoint via Expanso's `http` processor. No code, no service to run. Limited to whatever you can express in Bloblang.
2. **SDK sidecar** — a tiny FastAPI service uses the official Python SDK (`openai`, `anthropic`, `google-genai`). The pipeline routes events to it over HTTP. You get the SDK's batteries: retries, structured output, tool use, streaming.

The shared task across all six pipelines is **support-ticket classification**:

```
input:  {"id": "T-001", "message": "I was charged twice for my subscription"}
output: {"id": "T-001", "category": "billing", "sentiment": "neg", "priority": "high"}
```

Every pipeline reads the same `data/events.jsonl`, hits its provider, and writes the enriched event to stdout.

## Layout

```
demo-agents-sdk/
├── data/events.jsonl                # 8 sample tickets
├── pipelines/
│   ├── openai-http.yaml             # → api.openai.com directly
│   ├── openai-sdk.yaml              # → openai sidecar (port 8001)
│   ├── anthropic-http.yaml          # → api.anthropic.com directly
│   ├── anthropic-sdk.yaml           # → anthropic sidecar (port 8002)
│   ├── gemini-http.yaml             # → generativelanguage.googleapis.com
│   └── gemini-sdk.yaml              # → gemini sidecar (port 8003)
└── sidecars/
    ├── openai/      # FastAPI + openai SDK
    ├── anthropic/   # FastAPI + anthropic SDK
    └── gemini/      # FastAPI + google-genai SDK
```

## Quickstart

```bash
# 1. Set keys
cp .env.example .env
# Edit .env with your real OPENAI_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY

# 2. Validate pipelines (offline, no API calls)
for f in pipelines/*.yaml; do expanso-cli job validate --offline "$f"; done

# 3. Run an HTTP-direct demo (no sidecar needed)
docker compose run --rm openai-http
docker compose run --rm anthropic-http
docker compose run --rm gemini-http

# 4. Run an SDK sidecar demo
docker compose up -d openai-sidecar
docker compose run --rm openai-sdk
docker compose down
```

## How the two modes compare

| Concern               | HTTP-direct                     | SDK sidecar                          |
|-----------------------|---------------------------------|--------------------------------------|
| Lines of code         | 0 (YAML only)                   | ~60 per provider                     |
| Retry / backoff       | manual (`retries:` block)       | SDK default                          |
| Structured output     | `response_format: json_object`  | SDK pydantic / typed responses       |
| Tool use, streaming   | hard / not really               | first-class                          |
| Auth refresh          | static header                   | SDK handles ADC, OAuth, etc.         |
| What runs             | just Expanso                    | Expanso + N sidecars                 |

The pipelines are deliberately near-identical across modes — `diff pipelines/openai-http.yaml pipelines/openai-sdk.yaml` is a one-screen read.

## Deploying to production via Expanso Cloud

Local Docker Compose is for fast iteration. The production path is **Expanso Cloud → edge nodes**:

1. Push this repo to a Git remote your Expanso Cloud workspace can read.
2. In [cloud.expanso.io](https://cloud.expanso.io), register the pipeline YAMLs from `pipelines/` as jobs.
3. Set the API key secrets (`OPENAI_API_KEY`, etc.) in the workspace's secret store, not in the YAML.
4. Deploy each job to the target edge node group. The cloud orchestrator pushes the pipeline; edge nodes execute it.
5. For SDK-mode pipelines, the sidecars need to be reachable from edge nodes — either run them on the same node (sidecar pattern) or expose them as a shared service.

The HTTP-direct pipelines have zero infra dependencies — they're a pure pipeline definition. The SDK-sidecar pipelines trade that simplicity for SDK ergonomics; pick per-use-case.

## Models used

- OpenAI: `gpt-4o-mini`
- Anthropic: `claude-haiku-4-5-20251001`
- Gemini: `gemini-2.0-flash`

Override with `OPENAI_MODEL`, `ANTHROPIC_MODEL`, `GEMINI_MODEL` in `.env`.
