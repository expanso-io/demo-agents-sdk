# Runner image: Expanso Edge + uv + Python.
# Used for SDK-mode pipelines that run a Python classifier under the
# `subprocess` processor. uv self-bootstraps Python via `uv python install`.
#
# We layer uv on top of the official expanso-edge image rather than the other
# way around so the entrypoint and binary location stay canonical.

FROM ghcr.io/astral-sh/uv:latest AS uv

FROM ghcr.io/expanso-io/expanso-edge:nightly
COPY --from=uv /uv /uvx /usr/local/bin/

# Pre-install Python so first pipeline run doesn't pay the install cost.
# Dependencies are still resolved on first script invocation; uv caches them
# in /root/.cache/uv across subprocess restarts.
RUN uv python install 3.12 || true

# Allow uv to operate as root inside the container without warnings.
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1
