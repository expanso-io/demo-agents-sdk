# demo-agents-sdk

Built off potential user requirements for integrating cloud LLM SDKs directly into edge data pipelines.

Reference demo: **calling cloud LLM SDKs from inside an [Expanso Edge](https://expanso.io) pipeline.**

Each provider (OpenAI, Anthropic, Gemini) is shown two ways so you can see the trade-offs side-by-side:

1. **HTTP-direct** — the pipeline YAML calls the provider's REST endpoint via Expanso's `http` processor. No code, no extra container, no Python. Limited to whatever you can express in [Bloblang](https://docs.expanso.io/guides/bloblang).
2. **SDK via subprocess** — the pipeline runs a tiny Python script under Expanso's `subprocess` processor. The script imports the official SDK (`openai`, `anthropic`, `google-genai`) once at startup, then loops on stdin per message. You get the SDK's batteries — retries, structured output, streaming, tool use — without leaving the pipeline.

The shared task across all six pipelines is **support-ticket classification**:

```jsonc
// input
{"id": "T-001", "message": "I was charged twice for my subscription"}

// output
{"id": "T-001", "category": "billing", "sentiment": "neg", "priority": "high",
 "_provider": "openai", "_mode": "subprocess"}
```

Every pipeline reads the same `data/events.jsonl`, hits its provider, and writes the classified event to stdout.

---

## Run it (with real API keys)

You need: Docker, and at least one of OpenAI / Anthropic / Gemini API keys. You don't need all three — each provider's two pipelines run independently.

### 1. Get keys from the providers you want to use

| Provider  | Where to get a key                                                 | Looks like   |
|-----------|--------------------------------------------------------------------|--------------|
| OpenAI    | <https://platform.openai.com/api-keys>                             | `sk-...`     |
| Anthropic | <https://console.anthropic.com/settings/keys>                      | `sk-ant-...` |
| Gemini    | <https://aistudio.google.com/apikey>                               | `AIza...`    |

### 2. Drop the keys in a `.env` file

```bash
git clone https://github.com/expanso-io/demo-agents-sdk
cd demo-agents-sdk
cp .env.example .env
# edit .env — only fill in the providers you have keys for
```

The `.env` file is gitignored. Docker Compose picks it up automatically.

### 3. Build the runner image once

```bash
docker compose build openai-http
# ~90s first time; cached after that. All six services share this image.
```

### 4. Run any of the six demos

```bash
# HTTP-direct — pipeline YAML calls the API itself
docker compose run --rm openai-http
docker compose run --rm anthropic-http
docker compose run --rm gemini-http

# SDK via subprocess — pipeline shells out to a Python script using the official SDK
docker compose run --rm openai-sdk
docker compose run --rm anthropic-sdk
docker compose run --rm gemini-sdk
```

### What you'll see when it works

After ~5–10s of startup logs, you'll see eight JSON lines like:

```jsonc
{"id":"T-001","message":"I was charged twice...","category":"billing","sentiment":"neg","priority":"high","_provider":"openai","_mode":"http"}
{"id":"T-002","message":"The dashboard won't load...","category":"technical","sentiment":"neg","priority":"med","_provider":"openai","_mode":"http"}
...
```

The container will keep running (Expanso Edge stays up after the pipeline drains). Hit `Ctrl-C` to stop, then `docker compose down -v` to clean up.

---

## Layout

```
demo-agents-sdk/
├── Dockerfile                       # expanso-edge + expanso-cli + uv runner image
├── run-demo.sh                      # entrypoint: agent + cli deploy + tail logs
├── data/events.jsonl                # 8 sample tickets
├── scripts/
│   ├── openai_classify.py           # PEP 723: deps inline, runs via `uv run -s`
│   ├── anthropic_classify.py
│   └── gemini_classify.py
├── pipelines/
│   ├── openai-http.yaml             # http processor → api.openai.com
│   ├── openai-sdk.yaml              # subprocess → uv run -s openai_classify.py
│   ├── anthropic-http.yaml          # http processor → api.anthropic.com
│   ├── anthropic-sdk.yaml           # subprocess → anthropic_classify.py
│   ├── gemini-http.yaml             # http processor → generativelanguage.googleapis.com
│   └── gemini-sdk.yaml              # subprocess → gemini_classify.py
└── tests/                           # pytest unit + structure + smoke tests
```

## How the two modes compare

| Concern               | HTTP-direct                       | SDK via subprocess                       |
|-----------------------|-----------------------------------|------------------------------------------|
| Lines of code         | 0 (YAML only)                     | ~50 in one Python file                   |
| Retry / backoff       | manual (`retries:` field)         | SDK default (exponential, jitter)        |
| Structured output     | provider-specific YAML knobs      | SDK pydantic / typed responses           |
| Tool use, streaming   | hard / not really                 | first-class SDK features                 |
| Auth refresh          | static header                     | SDK handles ADC, OAuth, etc.             |
| What runs             | just expanso-edge                 | expanso-edge + Python child process      |
| Cold start            | none                              | once per pipeline run (uv warms cache)   |
| Concurrency           | per-message HTTP                  | one message at a time per subprocess     |

The pipeline YAML is *radically* simpler in SDK mode — `pipelines/openai-sdk.yaml` is 16 lines vs 50 for `openai-http.yaml`. All the provider-specific complexity moves into `scripts/openai_classify.py`, which gets to use the SDK's idioms instead of fighting Bloblang.

## How the runner image works

Every demo service uses a single image (`Dockerfile`) that layers `expanso-cli` and `uv` on top of `expanso-edge:nightly`. The `run-demo` entrypoint orchestrates the agent + CLI handshake that Expanso requires:

1. Starts `expanso-edge run --local` in the background
2. Waits for the local agent's API to come up
3. `expanso-cli job deploy <pipeline.yaml>` pushes the job to the local agent
4. Tails the agent so the pipeline's stdout flows out to the container

This is why `docker compose run --rm openai-http` "just works" without you needing to coordinate two processes by hand.

## How `subprocess` works under the hood

The Expanso `subprocess` processor spawns the command once and keeps it alive for the lifetime of the pipeline. Each message is written to the process's stdin (with a trailing newline by default), and the next line on stdout becomes the new message body. Two consequences worth knowing:

1. **You must `flush=True` after every line.** Without it, Python buffers stdout and the pipeline hangs waiting for output. Every script in `scripts/` does this.
2. **Errors stay inside the process.** The scripts catch exceptions and emit `{"error": "..."}` rows so a single bad message doesn't kill the subprocess (which would force Expanso to restart it from scratch).

## Tests

99 tests, no real API keys required.

```bash
make test         # fast tests (mocked SDKs, YAML structure, compose). 97 tests, ~1s.
make test-smoke   # E2E pipeline test through Docker with a stub classifier. 2 tests, ~5s warm.
make test-all     # both
make verify       # lint + fast tests + pipeline validation + compose config (CI parity)
```

The smoke test deliberately uses a stub classifier so it works for anyone who clones the repo, without any API keys. The unit tests mock each SDK client.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Error = edge needs to be bootstrapped` | Missing `--local` flag | The `run-demo` entrypoint adds it; if you're invoking `expanso-edge run` by hand, append `--local` |
| Container starts but no JSON output | Python script not flushing stdout | Confirm `print(..., flush=True)` in your classifier |
| `401 Unauthorized` from the provider | `.env` not loaded or wrong key | `docker compose config` — under `services.<name>.environment` you should see `<PROVIDER>_API_KEY=<your-key>` |
| Pipeline hangs forever | Subprocess exited and Expanso is restarting it | Check `docker compose logs <service>` — usually a Python traceback |
| `429 rate limited` | Free-tier quota | Wait or supply a paid key; SDK mode handles backoff automatically, HTTP mode honors the YAML's `retries:` block |
| First SDK pipeline run is slow (~30s) | uv resolving SDK deps the first time | Subsequent runs share the `uv-cache` named volume and start in <2s |

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

## License

[Apache 2.0](./LICENSE).
