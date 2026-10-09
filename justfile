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
    uv run --no-project scripts/stop-owned.py record --pidfile .runtime/explorer.pid --match "http.server"
    @for _ in $(seq 1 50); do curl -fsS -o /dev/null http://127.0.0.1:{{PORT}}/explorer/index.html 2>/dev/null && break; sleep 0.1; done
    @echo "Cloud jobs deployed; explorer on http://127.0.0.1:{{PORT}}/explorer/"

# Fixture-only local run; no Cloud account or model call.
up-offline: _ports-check
    docker compose run --rm gateway-http
    docker compose run --rm gateway-subprocess
    mkdir -p .runtime
    nohup uv run --no-project python -m http.server {{PORT}} --bind 127.0.0.1 > .runtime/explorer.log 2>&1 & echo $! > .runtime/explorer.pid
    uv run --no-project scripts/stop-owned.py record --pidfile .runtime/explorer.pid --match "http.server"
    @for _ in $(seq 1 50); do curl -fsS -o /dev/null http://127.0.0.1:{{PORT}}/explorer/index.html 2>/dev/null && break; sleep 0.1; done
    @echo "explorer on http://127.0.0.1:{{PORT}}/explorer/ (just down stops it)"

gateway-up: _gateway-ports-check
    mkdir -p .runtime
    nohup uv run -s ../_demo-kit/model-gateway.py serve --config model-gateway.toml --port {{MODEL_GATEWAY_PORT}} > .runtime/gateway.log 2>&1 & echo $! > .runtime/gateway.pid
    uv run --no-project scripts/stop-owned.py record --pidfile .runtime/gateway.pid --match "model-gateway.py"
    @echo "model gateway on http://127.0.0.1:{{MODEL_GATEWAY_PORT}} (${GATEWAY_MODE:-fixture})"

gateway-down:
    uv run --no-project scripts/stop-owned.py stop --pidfile .runtime/gateway.pid --match "model-gateway.py"

gateway-status:
    @uv run -s ../_demo-kit/model-gateway.py status --config model-gateway.toml --port {{MODEL_GATEWAY_PORT}}

provider-check:
    @uv run -s ../_demo-kit/lint-demo-providers.py .

pipeline-check:
    @uv run -s ../_demo-kit/lint-demo-pipelines.py .

test:
    @make test

check: provider-check pipeline-check ownership-check
    @make verify

# Stop this demo's Cloud jobs and local node, then prove ports are free.
down: gateway-down
    -expanso-cli job stop gateway-http --force
    -expanso-cli job stop gateway-subprocess --force
    uv run --no-project scripts/stop-owned.py stop --pidfile .runtime/explorer.pid --match "http.server"
    -docker compose -f deploy/docker-compose.node.yaml down
    -docker compose down -v --remove-orphans
    uv run --no-project scripts/stop_local.py {{MODEL_GATEWAY_PORT}} {{PORT}}
    @echo "down: ports {{MODEL_GATEWAY_PORT}} and {{PORT}} are free"

ports:
    @printf '%s\n' '{{ports_json}}'

[private]
_ports-check:
    @uv run --no-project scripts/demo-ports.py resolve --demo-dir . --service PORT >/dev/null

[private]
_gateway-ports-check:
    @uv run --no-project scripts/demo-ports.py resolve --demo-dir . --service MODEL_GATEWAY_PORT >/dev/null

ownership-check:
    uv run --no-project scripts/test_stop_owned.py
