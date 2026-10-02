set shell := ["bash", "-euo", "pipefail", "-c"]

_default:
    @just --list

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

down: gateway-down
    -docker compose down -v
