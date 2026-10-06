#!/usr/bin/env bash
# Entrypoint for the one-shot runner containers.
#
# Usage: run-demo pipelines/<name>.yaml
#
# Starts the replay gateway, starts expanso-edge in --local mode, deploys the
# pipeline with expanso-cli and passes the edge output through. `expanso-edge
# run --local foo.yaml` ignores the YAML argument: the agent and the deploy
# step are separate processes, and both have to be invoked.
#
# EXPECT_RECORDS=N bounds the run. The wrapper counts output records (lines
# that start with `{`). Once N have appeared it stops edge with SIGTERM, then
# the gateway, and exits 0. It exits 1 if they do not appear within
# RUN_TIMEOUT_S (default 120). Without EXPECT_RECORDS it runs until SIGTERM
# or Ctrl-C.

set -euo pipefail

PIPELINE="${1:?usage: run-demo pipelines/<name>.yaml}"
EXPECT_RECORDS="${EXPECT_RECORDS:-0}"
RUN_TIMEOUT_S="${RUN_TIMEOUT_S:-120}"
GATEWAY_PORT="${GATEWAY_PORT:-18157}"
WORK="$(mktemp -d)"
OUT="$WORK/edge.out"
GATEWAY_PID=""
EDGE_PID=""

if [[ ! -f "$PIPELINE" ]]; then
  echo "run-demo: pipeline file not found: $PIPELINE" >&2
  exit 2
fi

stop() {
  local pid="$1"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  fi
}

cleanup() {
  trap - EXIT INT TERM
  stop "$EDGE_PID"
  stop "$GATEWAY_PID"
  rm -rf "$WORK"
}
trap cleanup EXIT INT TERM

python3 gateway/fixture_gateway.py --port "$GATEWAY_PORT" &
GATEWAY_PID=$!
for _ in $(seq 1 50); do
  curl -fsS "http://127.0.0.1:$GATEWAY_PORT/status" >/dev/null 2>&1 && break
  sleep 0.1
done
if ! curl -fsS "http://127.0.0.1:$GATEWAY_PORT/status" >/dev/null; then
  echo "run-demo: replay gateway did not become ready" >&2
  exit 1
fi

expanso-edge run --local --no-watch --config config/edge-local.yaml \
  --data-dir "$WORK/edge" > >(tee "$OUT") 2>&1 &
EDGE_PID=$!

# The agent API comes up a moment after the process starts.
for _ in $(seq 1 60); do
  expanso-cli node list >/dev/null 2>&1 && break
  sleep 0.5
done

expanso-cli job deploy "$PIPELINE"

if [[ "$EXPECT_RECORDS" -gt 0 ]]; then
  deadline=$((SECONDS + RUN_TIMEOUT_S))
  while ((SECONDS < deadline)); do
    seen="$(grep -c '^{' "$OUT" || true)"
    if [[ "$seen" -ge "$EXPECT_RECORDS" ]]; then
      echo "run-demo: $seen of $EXPECT_RECORDS records seen, stopping edge" >&2
      sleep 1
      exit 0
    fi
    sleep 0.5
  done
  echo "run-demo: expected $EXPECT_RECORDS records, saw ${seen:-0}" >&2
  exit 1
fi

wait "$EDGE_PID"
