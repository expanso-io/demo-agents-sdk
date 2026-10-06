# demo-agents-sdk

Two [Expanso Edge](https://expanso.io) pipelines classify the same four
support tickets by asking one local model gateway. They differ in where the
request is built:

1. `gateway-http` builds it in pipeline YAML with a branch and an HTTP call.
2. `gateway-subprocess` keeps a small Python client alive under the Expanso
   `subprocess` processor.

Open [`explorer/index.html`](explorer/index.html) to walk any ticket through
every stage of either pipeline. Each stage shows the real input, the real
output and the exact pipeline text, captured from Expanso Edge runs of the
files in this repository.

The gateway replays answers that were recorded once and committed under
`fixtures/model/`, so a run makes no model call. A ticket with no recorded
answer is refused, and both pipelines turn that into an error record.

## Run it

You need Docker. No credential, model key or sibling checkout is needed.

```bash
docker compose run --rm gateway-http
docker compose run --rm gateway-subprocess
```

Each container starts the replay gateway and Expanso Edge, deploys one
pipeline, prints four records and exits 0 on its own. It runs as an
unprivileged user on a read-only root with every capability dropped.

```json
{
  "_gateway_source": "fixture",
  "_mode": "http",
  "category": "billing",
  "id": "T-001",
  "message": "I was charged twice for my Pro subscription this month. Please refund the duplicate charge ASAP.",
  "priority": "high",
  "sentiment": "neg"
}
```

The expected records for both pipelines are in `expected/`. The latest dated
run, with tool versions, input and output digests, and the failure record, is
in [`reports/`](reports/).

## Deploy to Expanso Cloud

The node runs two containers that share one network namespace. The replay
gateway listens on loopback inside it and publishes no port, so the address
the pipelines call, `127.0.0.1:18157`, is the colocated gateway. The Edge
identity and message buffer persist in the `edge-data` volume.

1. Copy `.env.example` to `.env` and set `EXPANSO_EDGE_BOOTSTRAP_TOKEN` to
   the token from Expanso Cloud. The file is git-ignored.
2. Enroll the node once:

   ```bash
   docker compose -f deploy/docker-compose.node.yaml \
     --profile enroll run --rm enroll
   ```

3. Start the gateway and Edge:

   ```bash
   docker compose -f deploy/docker-compose.node.yaml up -d
   ```

4. Deploy a pipeline with your project's Expanso CLI profile. The job
   selector `demo: demo-agents-sdk` matches the node label in
   `config/edge-node.yaml`:

   ```bash
   expanso-cli job deploy pipelines/gateway-http.yaml
   ```

5. Confirm the node is connected with `expanso-cli node list`, then open the
   job in Expanso Cloud. Logs show one line per ticket.

The node needs outbound access to Expanso Cloud and nothing else. Stop it
with `docker compose -f deploy/docker-compose.node.yaml down`; add `-v` only
to discard the enrolled identity.

## Prove it

```bash
uv run -s scripts/prove.py --check --node
```

This builds the image, runs both pipelines, compares their records with
`expected/`, rebuilds every per-stage fixture and the explorer data from real
Edge runs, fails if the committed copies differ, brings up the node stack in
local mode, and writes the dated report. Enrolling in Expanso Cloud needs a
token and is not part of it.

## Record replacement answers

Recording happens on the host through the demo-kit gateway and never in the
runners. It requires an explicit subscription backend when the gateway
starts. Ask one prompt at a time and never drive live mode from browser
automation or a retrying loop. See the Models section of
`../_demo-kit/README.md` for the recording and kill-switch controls.

```bash
just gateway-up
just gateway-status
just gateway-down
```

## Layout

```text
demo-agents-sdk/
├── data/events.jsonl            the four shipped tickets
├── expected/                    expected records for each pipeline
├── fixtures/model/              recorded model answers
├── fixtures/stages/             input and output of every explorer stage
├── pipelines/                   the two pipelines and explorer.json
├── gateway/fixture_gateway.py   replay-only gateway
├── scripts/                     Python client, proof and explorer build
├── explorer/                    the step explorer
├── deploy/                      Cloud node stack
├── config/                      Edge node settings
├── reports/                     dated run reports
├── public-bar.toml              inventory read by the shared public-bar check
├── public-features.json         features that must be kept
└── public-removals/             approved and pending removals
```

## Checks

```bash
just check          # lint, tests, pipeline lint, validation, explorer
make test-smoke     # both pipelines in Docker against expected/
```

`.github/workflows/ci.yml` runs the same gates, the proof run, and the shared
public-bar check.

## Features removed earlier, waiting for a decision

Commit `46abdb5` moved every model request behind the gateway and removed the
original provider comparison. Restoring it would call providers directly,
which the demo-kit provider check and the gateway rule forbid, so these wait
for a captain decision. They are recorded in
[`public-removals/pending-captain.json`](public-removals/pending-captain.json).

- The three provider-specific HTTP pipelines.
- The three provider SDK pipelines, their client scripts, tests and `uv.lock`.
- Tickets T-005 to T-008. Restoring them needs four more recorded answers,
  which means model calls, and the gateway caps a run at four.

## License

[Apache 2.0](./LICENSE)
