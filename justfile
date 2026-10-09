set shell := ["bash", "-euo", "pipefail", "-c"]

# Resolve once; down retains the persistent allocation.
ports_json := shell("uv run --no-project scripts/demo-ports.py resolve --demo-dir . --allow-bound")
export PORT := shell("printf '%s' '" + ports_json + "' | jq -r .PORT")
export MODEL_GATEWAY_PORT := shell("printf '%s' '" + ports_json + "' | jq -r .MODEL_GATEWAY_PORT")

_default:
    @just --list

# Start the Cloud-connected node and deploy or update both Cloud pipelines.
up: _ports-check
    docker compose -f deploy/docker-compose.node.yaml up -d
    expanso-cli job deploy --force pipelines/gateway-http.yaml
    expanso-cli job deploy --force pipelines/gateway-subprocess.yaml
    mkdir -p .runtime
    nohup uv run --no-project python -m http.server {{PORT}} --bind 127.0.0.1 > .runtime/explorer.log 2>&1 & echo $! > .runtime/explorer.pid
    @for _ in $(seq 1 50); do curl -fsS -o /dev/null http://127.0.0.1:{{PORT}}/explorer/index.html 2>/dev/null && break; sleep 0.1; done
    @echo "Cloud jobs deployed; explorer on http://127.0.0.1:{{PORT}}/explorer/"

# Fixture-only local run; no Cloud account or model call.
up-offline: _ports-check
    docker compose run --rm gateway-http
    docker compose run --rm gateway-subprocess
    mkdir -p .runtime
    nohup uv run --no-project python -m http.server {{PORT}} --bind 127.0.0.1 > .runtime/explorer.log 2>&1 & echo $! > .runtime/explorer.pid
    @for _ in $(seq 1 50); do curl -fsS -o /dev/null http://127.0.0.1:{{PORT}}/explorer/index.html 2>/dev/null && break; sleep 0.1; done
    @echo "explorer on http://127.0.0.1:{{PORT}}/explorer/ (just down stops it)"

gateway-up:
    mkdir -p .runtime
    nohup uv run -s ../_demo-kit/model-gateway.py serve --config model-gateway.toml --port {{MODEL_GATEWAY_PORT}} > .runtime/gateway.log 2>&1 & echo $! > .runtime/gateway.pid
    @echo "model gateway on http://127.0.0.1:{{MODEL_GATEWAY_PORT}} (${GATEWAY_MODE:-fixture})"

gateway-down:
    -[ -f .runtime/gateway.pid ] && kill "$(cat .runtime/gateway.pid)" 2>/dev/null && rm .runtime/gateway.pid

gateway-status:
    @uv run -s ../_demo-kit/model-gateway.py status --config model-gateway.toml --port {{MODEL_GATEWAY_PORT}}

provider-check:
    @uv run -s ../_demo-kit/lint-demo-providers.py .

pipeline-check:
    @uv run -s ../_demo-kit/lint-demo-pipelines.py .

test:
    @make test

check: provider-check pipeline-check
    @make verify

# Stop this demo's Cloud jobs and local node, then prove ports are free.
down: gateway-down
    -expanso-cli job stop gateway-http --force
    -expanso-cli job stop gateway-subprocess --force
    -[ -f .runtime/explorer.pid ] && kill "$(cat .runtime/explorer.pid)" 2>/dev/null; rm -f .runtime/explorer.pid
    -docker compose -f deploy/docker-compose.node.yaml down
    -docker compose down -v --remove-orphans
    python3 scripts/stop_local.py {{MODEL_GATEWAY_PORT}} {{PORT}}
    @echo "down: ports {{MODEL_GATEWAY_PORT}} and {{PORT}} are free"

ports:
    @printf '%s\n' '{{ports_json}}'

[private]
_ports-check:
    @uv run --no-project scripts/demo-ports.py resolve --demo-dir . >/dev/null
