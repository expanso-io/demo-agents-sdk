#!/usr/bin/env bash
# Entrypoint for demo runner containers.
#
# Usage: run-demo /pipelines/<name>.yaml
#
# Starts expanso-edge in --local mode, waits for its API, deploys the given
# pipeline via expanso-cli, then tails edge stdout so the pipeline's output
# (which goes to the edge process's stdout) shows up on the container's
# stdout. SIGTERM / Ctrl-C stops both.
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

# Start the agent in the background. Capture its PID so we can shut it down.
expanso-edge run --local --no-watch &
EDGE_PID=$!

cleanup() {
  if kill -0 "$EDGE_PID" 2>/dev/null; then
    kill -TERM "$EDGE_PID" 2>/dev/null || true
    wait "$EDGE_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

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
