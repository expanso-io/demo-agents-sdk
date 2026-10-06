# Runner and node image: Expanso Edge, Expanso CLI, Python 3, the replay
# gateway and the demo files. The same image runs the local one-shot proof
# (docker-compose.yaml) and the Cloud-enrolled node (deploy/).
#
# Edge and the CLI are pinned to one release; the base is pinned by digest.
# It runs as the base image's unprivileged `expanso` user (uid 1000).

FROM ghcr.io/expanso-io/expanso-edge:v2.1.22@sha256:0a119d5cd7cc5c889d0d57a468e16ffb892134a5a4e4b2e5d529e4c0ad1a3ecb

USER root

# Python runs the subprocess classifier and the replay gateway; curl is the
# readiness probe. Both need only the standard library.
RUN apk add --no-cache python3 curl ca-certificates bash \
 && curl -fsSL https://get.expanso.io/cli/install.sh \
    | EXPANSO_INSTALL_DIR=/usr/local/bin EXPANSO_VERSION=v2.1.22 bash \
 && expanso-cli version

COPY --chown=expanso:expanso run-demo.sh /usr/local/bin/run-demo
COPY --chown=expanso:expanso gateway /opt/demo/gateway
COPY --chown=expanso:expanso scripts /opt/demo/scripts
COPY --chown=expanso:expanso config /opt/demo/config
COPY --chown=expanso:expanso data /opt/demo/data
COPY --chown=expanso:expanso fixtures /opt/demo/fixtures
COPY --chown=expanso:expanso pipelines /opt/demo/pipelines
RUN chmod 0555 /usr/local/bin/run-demo

# Pipelines use paths relative to the node's working directory.
WORKDIR /opt/demo
USER expanso
ENTRYPOINT ["run-demo"]
