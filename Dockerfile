# Runner image: Expanso Edge + Expanso CLI + uv + Python.
#
# Used by every demo service in docker-compose.yaml. The two Expanso binaries
# work together:
#   - expanso-edge runs the agent that executes pipelines
#   - expanso-cli deploys pipeline YAMLs against the local agent's API
# An entrypoint wrapper (run-demo.sh) orchestrates them so a single
# `docker compose run` lifts both up and tears down cleanly.
#
# uv runs the standard-library gateway client and the mounted demo-kit gateway.

FROM ghcr.io/astral-sh/uv:latest AS uv

FROM ghcr.io/expanso-io/expanso-edge:nightly

# Base image runs as `expanso` (uid 1000) by default. We need root to install
# packages and add binaries; the final USER directive drops back.
USER root

# Layer 1: uv (multi-stage copy from the official image, no apt needed).
COPY --from=uv /uv /uvx /usr/local/bin/

# Layer 2: expanso-cli (official installer downloads matching arch binary).
# Base image is Alpine — apk + bash for the installer. install.sh writes to
# /usr/local/bin by default when EXPANSO_INSTALL_DIR is set.
RUN apk add --no-cache curl ca-certificates bash \
 && curl -fsSL https://get.expanso.io/cli/install.sh \
    | EXPANSO_INSTALL_DIR=/usr/local/bin bash \
 && expanso-cli version

# Layer 3: pre-install Python so first pipeline run doesn't pay the cost.
RUN uv python install 3.12 || true

# Layer 4: entrypoint wrapper.
COPY run-demo.sh /usr/local/bin/run-demo
RUN chmod +x /usr/local/bin/run-demo

# uv cache + edge data dir need to be writable by the runtime user.
RUN mkdir -p /root/.cache/uv && chmod -R 777 /root/.cache

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# Run as root for the demo — the agent + cli + uv all need to write to the
# same paths and the friction of juggling permissions isn't worth it for
# local iteration.
ENTRYPOINT ["run-demo"]
