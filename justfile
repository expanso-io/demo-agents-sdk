set shell := ["bash", "-euo", "pipefail", "-c"]

_default:
    @just --list

# Run both pipelines in their one-shot runners, then serve the explorer.
up:
    docker compose run --rm gateway-http
    docker compose run --rm gateway-subprocess
    mkdir -p .runtime
    nohup python3 -m http.server 18160 --bind 127.0.0.1 > .runtime/explorer.log 2>&1 & echo $! > .runtime/explorer.pid
    @for _ in $(seq 1 50); do curl -fsS -o /dev/null http://127.0.0.1:18160/explorer/index.html 2>/dev/null && break; sleep 0.1; done
    @echo "explorer on http://127.0.0.1:18160/explorer/ (just down stops it)"

gateway-up:
    mkdir -p .runtime
    nohup uv run -s ../_demo-kit/model-gateway.py serve --config model-gateway.toml > .runtime/gateway.log 2>&1 & echo $! > .runtime/gateway.pid
    @echo "model gateway on http://127.0.0.1:18157 (${GATEWAY_MODE:-fixture})"

gateway-down:
    -[ -f .runtime/gateway.pid ] && kill "$(cat .runtime/gateway.pid)" 2>/dev/null && rm .runtime/gateway.pid

gateway-status:
    @uv run -s ../_demo-kit/model-gateway.py status --config model-gateway.toml

provider-check:
    @uv run -s ../_demo-kit/lint-demo-providers.py .

pipeline-check:
    @uv run -s ../_demo-kit/lint-demo-pipelines.py .

test:
    @make test

check: provider-check pipeline-check
    @make verify

# Stop the explorer and gateway, remove runner containers, prove ports are free.
down: gateway-down
    -[ -f .runtime/explorer.pid ] && kill "$(cat .runtime/explorer.pid)" 2>/dev/null; rm -f .runtime/explorer.pid
    -docker compose down -v --remove-orphans
    python3 scripts/stop_local.py 18157 18160
    @echo "down: ports 18157 and 18160 are free"
