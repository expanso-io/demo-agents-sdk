# demo-agents-sdk

Reference demo: calling the demo-kit model gateway from an
[Expanso Edge](https://expanso.io) pipeline.

The original version called three model providers directly, both from pipeline
HTTP processors and from provider SDKs. This version keeps the useful
integration comparison while putting every model request through one guarded,
localhost-only gateway:

1. `gateway-http` builds the gateway request in pipeline YAML.
2. `gateway-subprocess` keeps a small Python gateway client alive under the
   Expanso `subprocess` processor.

Both classify the same four support tickets. Fixture replay is the default, so
the normal demo makes zero live model calls. The committed answers were
recorded through the gateway from a subscription backend. The gateway enforces
single-flight execution, caching, a kill switch, and caps of four calls per run
and four calls per minute.

## Run it

You need Docker and the sibling `_demo-kit` directory. No model credential or
metered key is needed.

```bash
docker compose run --rm gateway-http
docker compose run --rm gateway-subprocess
```

Each runner mounts `_demo-kit` read-only and starts the model gateway inside
the same container as Expanso Edge. Once the four events drain, press `Ctrl-C`
to stop the local Edge process. `just down` removes any remaining containers,
volumes, and a host gateway started by this demo.

Successful output contains four JSON records like this:

```json
{
  "id": "T-001",
  "category": "billing",
  "sentiment": "neg",
  "priority": "high",
  "_gateway_source": "fixture",
  "_mode": "http"
}
```

## Gateway controls

The host recipes are useful for testing the Python client and deliberately
recording replacements. They never select live mode by default.

```bash
just gateway-up
just gateway-status
just gateway-down
```

Live recording requires an explicit subscription backend when the gateway
starts. Ask one prompt at a time through the gateway CLI. Never drive live mode
from browser automation or a retrying loop. See the Models section in
`../_demo-kit/README.md` for the exact recording and kill-switch controls.

## Layout

```text
demo-agents-sdk/
├── data/events.jsonl
├── fixtures/model/
├── model-gateway.toml
├── pipelines/
│   ├── gateway-http.yaml
│   └── gateway-subprocess.yaml
├── scripts/gateway_classify.py
├── docker-compose.yaml
└── tests/
```

The HTTP path has no child process. The subprocess path is convenient when
request validation, response parsing, or other application logic belongs in
ordinary code. Neither path knows which subscription backend produced a
fixture or might serve a deliberate live request.

## Checks

```bash
just check
make test-smoke
```

`just check` runs the direct-provider linter, Ruff, unit and structure tests,
offline Expanso pipeline validation, and Docker Compose validation. The smoke
test builds the runner image and proves the Expanso subprocess flow end to end
with a deterministic test double.

## Expanso Cloud

The pipelines are valid Expanso jobs, but the gateway is intentionally bound
to localhost. A Cloud-managed edge deployment must colocate the gateway on the
selected node and provide the committed fixture pack there. This repository
does not provision that node-side service, so the verified main flow is local
fixture replay rather than a Cloud execution.

## License

[Apache 2.0](./LICENSE)
