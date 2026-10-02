#!/usr/bin/env bash
# Entrypoint for demo runner containers.
#
# Usage: run-demo /pipelines/<name>.yaml
#
# Starts the fixture-mode model gateway when MODEL_GATEWAY_CONFIG is set,
# then starts expanso-edge in --local mode, deploys the pipeline, and tails
# edge stdout. SIGTERM / Ctrl-C stops every process started here.
#
# Without this wrapper, `expanso-edge run --local foo.yaml` ignores the YAML
# argument — the agent and the CLI deploy step are separate processes and
# both have to be invoked.

set -euo pipefail

PIPELINE="${1:?usage: run-demo /pipelines/<name>.yaml}"

if [[ ! -f "$PIPELINE" ]]; then
  echo "run-demo: pipeline file not found: $PIPELINE" >&2
  exit 2
fi

GATEWAY_PID=""
EDGE_PID=""

cleanup() {
  if [[ -n "$EDGE_PID" ]] && kill -0 "$EDGE_PID" 2>/dev/null; then
    kill -TERM "$EDGE_PID" 2>/dev/null || true
    wait "$EDGE_PID" 2>/dev/null || true
  fi
  if [[ -n "$GATEWAY_PID" ]] && kill -0 "$GATEWAY_PID" 2>/dev/null; then
    kill -TERM "$GATEWAY_PID" 2>/dev/null || true
    wait "$GATEWAY_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

if [[ -n "${MODEL_GATEWAY_CONFIG:-}" ]]; then
  if [[ ! -f /demo-kit/model-gateway.py ]]; then
    echo "run-demo: /demo-kit/model-gateway.py is not mounted" >&2
    exit 2
  fi
  uv run -s /demo-kit/model-gateway.py serve \
    --config "$MODEL_GATEWAY_CONFIG" &
  GATEWAY_PID=$!
  for _ in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:18157/status >/dev/null 2>&1; then
      break
    fi
    sleep 0.2
  done
  if ! curl -fsS http://127.0.0.1:18157/status >/dev/null; then
    echo "run-demo: model gateway did not become ready" >&2
    exit 1
  fi
fi

# Start the agent in the background. Capture its PID so we can shut it down.
expanso-edge run --local --no-watch &
EDGE_PID=$!

# Wait for the agent's API to come up. Edge logs the listen address but the
# port is consistent (9010 by default in --local mode).
for _ in $(seq 1 30); do
  if expanso-cli node list >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

expanso-cli job deploy "$PIPELINE"

# Hand off to the edge process — its stdout carries the pipeline's output.
wait "$EDGE_PID"
