#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Run the published pipelines in the runner image and record what they did.

    uv run -s scripts/prove.py            run, check, write explorer + report
    uv run -s scripts/prove.py --check    run, then fail if the committed
                                          explorer contract differs
    uv run -s scripts/prove.py --node     also bring up the Cloud node stack
                                          in local mode and call the gateway

Every number and record it writes comes from a real Expanso Edge run in the
image. Per-stage views run the real pipeline cut after that stage, one ticket
per container, and read the message Edge emits. The client and gateway views
call the same Python and the same replay gateway the pipelines use. It makes
no model call: the gateway only replays the committed fixtures.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import http.server
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "gateway"))

import fixture_gateway  # noqa: E402
import gateway_classify  # noqa: E402

IMAGE = "demo-agents-sdk-runner:prove"
PROJECT = "agents-sdk-prove"
CONTRACT = ROOT / "pipelines" / "explorer.json"
FAILURE = {
    "id": "T-900",
    "message": "Can I change the invoice currency from USD to EUR for next month?",
}
HARDENING = [
    "--read-only",
    "--cap-drop",
    "ALL",
    "--security-opt",
    "no-new-privileges:true",
    "--tmpfs",
    "/tmp:uid=1000,gid=1000,mode=0700",
    "-e",
    "HOME=/tmp",
]


def sh(*args: str, check: bool = True, **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=check, **kwargs)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tickets() -> list[dict]:
    lines = (ROOT / "data" / "events.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


# ------------------------------------------------------------------ Docker


def build_image() -> None:
    sh("docker", "build", "--quiet", "-t", IMAGE, ".", cwd=ROOT)


def run_pipeline(
    pipeline: str, expect: int, mounts: dict[Path, str] | None = None
) -> tuple[list[str], str, int]:
    """Run one pipeline file in a fresh container. Return output records,
    the full container output and the exit code."""
    name = f"{PROJECT}-{uuid.uuid4().hex[:10]}"
    command = ["docker", "run", "--rm", "--name", name, *HARDENING]
    command += ["-e", f"EXPECT_RECORDS={expect}"]
    for host, target in (mounts or {}).items():
        command += ["-v", f"{host}:{target}:ro"]
    command += [IMAGE, pipeline]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=240, check=False)
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
    output = result.stdout + result.stderr
    records = [line for line in result.stdout.splitlines() if line.startswith("{")]
    return records, output, result.returncode


# ------------------------------------------------------------------ pipeline cuts


def load_pipeline(name: str) -> dict:
    return yaml.safe_load((ROOT / "pipelines" / f"{name}.yaml").read_text())


def variant(
    name: str, ticket_file: str, keep: int | None, edit: dict[int, dict] | None = None
) -> dict:
    """The real pipeline with its input pointed at one ticket and its
    processor list cut after `keep` stages (None keeps all but the log)."""
    doc = load_pipeline(name)
    config = doc["config"]
    config["input"]["file"]["paths"] = [ticket_file]
    processors = [p for p in config["pipeline"]["processors"] if p.get("label") != "log_result"]
    if keep is not None:
        processors = processors[:keep]
    for index, replacement in (edit or {}).items():
        processors[index] = replacement
    config["pipeline"]["processors"] = processors
    doc.pop("selector", None)
    return doc


def request_map_variant(name: str, ticket_file: str) -> dict:
    """Parse, then apply the branch's own request_map as a plain mapping."""
    doc = variant(name, ticket_file, 2)
    branch = doc["config"]["pipeline"]["processors"][1]["branch"]
    doc["config"]["pipeline"]["processors"][1] = {
        "label": "request_map",
        "mapping": branch["request_map"],
    }
    return doc


def reply_variant(name: str, ticket_file: str) -> dict:
    """The branch's own request_map and http call, keeping the raw reply."""
    doc = variant(name, ticket_file, 2)
    branch = doc["config"]["pipeline"]["processors"][1]["branch"]
    branch["result_map"] = "root = this"
    return doc


def edge_message(name: str, doc: dict, ticket: dict, workdir: Path) -> dict | str:
    """Run `doc` on one ticket in the image and return the message Edge emits."""
    stem = f"{name}-{ticket['id']}-{uuid.uuid4().hex[:6]}"
    (workdir / f"{stem}.jsonl").write_text(json.dumps(ticket) + "\n")
    doc["config"]["input"]["file"]["paths"] = [f"variants/{stem}.jsonl"]
    (workdir / f"{stem}.yaml").write_text(yaml.safe_dump(doc, sort_keys=False, width=1000))
    records, output, code = run_pipeline(
        f"variants/{stem}.yaml", expect=1, mounts={workdir: "/opt/demo/variants"}
    )
    if code != 0 or len(records) != 1:
        raise SystemExit(
            f"{name} {ticket['id']}: exit {code}, {len(records)} records\n{output[-2000:]}"
        )
    return json.loads(records[0])


# ------------------------------------------------------------------ gateway view


class Gateway:
    """The replay gateway on a free local port, for the direct client views."""

    def __enter__(self) -> Gateway:
        replay = fixture_gateway.Replay(ROOT / "fixtures" / "model")
        self.server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), fixture_gateway.make_handler(replay)
        )
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/ask"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        gateway_classify.GATEWAY_URL = self.url
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()

    def reply(self, body: dict) -> dict:
        request = urllib.request.Request(
            self.url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return {"http_status": response.status, "body": json.loads(response.read())}
        except urllib.error.HTTPError as error:
            return {"http_status": error.code, "body": json.loads(error.read())}


# ------------------------------------------------------------------ YAML excerpts


def excerpt(path: str, start: str) -> str:
    """Exact lines of a file from the line starting with `start` up to, but not
    including, the next non-blank line at the same or a shallower indent. Keeps
    the published text and the explorer in step."""
    lines = (ROOT / path).read_text().splitlines()
    first = next(i for i, line in enumerate(lines) if line.strip().startswith(start))
    indent = len(lines[first]) - len(lines[first].lstrip())
    taken = [lines[first]]
    for line in lines[first + 1 :]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        taken.append(line)
    return textwrap.dedent("\n".join(taken)).rstrip()


def processor_block(path: str, label: str) -> str:
    lines = (ROOT / path).read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == f"- label: {label}")
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        current = len(lines[i]) - len(lines[i].lstrip())
        if stripped and (current < indent or (current == indent and stripped.startswith("- "))):
            end = i
            break
    return textwrap.dedent("\n".join(lines[start:end])).rstrip()


def block_between(path: str, begin: str, end: str | None) -> str:
    lines = (ROOT / path).read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip().startswith(begin))
    stop = len(lines)
    if end:
        stop = next(i for i in range(start + 1, len(lines)) if lines[i].strip().startswith(end))
    return textwrap.dedent("\n".join(lines[start:stop])).rstrip()


# ------------------------------------------------------------------ explorer contract


HTTP = "pipelines/gateway-http.yaml"
SUB = "pipelines/gateway-subprocess.yaml"


def stage(stage_id: str, title: str, component: str, about: str, code: str, io: dict) -> dict:
    return {
        "id": stage_id,
        "title": title,
        "component": component,
        "about": about,
        "code": code,
        "io": io,
    }


def capture(all_tickets: list[dict]) -> dict:
    ids = [t["id"] for t in all_tickets]
    with tempfile.TemporaryDirectory(prefix="agents-sdk-variants-") as tmp, Gateway() as gateway:
        workdir = Path(tmp)
        workdir.chmod(0o755)
        jobs: dict[tuple[str, str, str], tuple[str, dict, dict]] = {}
        for ticket in all_tickets:
            tid = ticket["id"]
            for key, name, doc in (
                ("raw", "gateway-http", variant("gateway-http", "", 0)),
                ("parsed", "gateway-http", variant("gateway-http", "", 1)),
                ("request", "gateway-http", request_map_variant("gateway-http", "")),
                ("reply", "gateway-http", reply_variant("gateway-http", "")),
                ("asked", "gateway-http", variant("gateway-http", "", 2)),
                ("caught", "gateway-http", variant("gateway-http", "", None)),
                ("client", "gateway-subprocess", variant("gateway-subprocess", "", None)),
            ):
                jobs[(key, name, tid)] = (name, doc, ticket)
        results: dict[tuple[str, str, str], dict | str] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(edge_message, name, doc, ticket, workdir): key
                for key, (name, doc, ticket) in jobs.items()
            }
            for future in concurrent.futures.as_completed(futures):
                results[futures[future]] = future.result()

        def out(key: str, name: str, tid: str):
            return results[(key, name, tid)]

        client_request, client_reply = {}, {}
        for ticket in all_tickets:
            body = gateway_classify.build_request(ticket["message"], "support-" + ticket["id"])
            client_request[ticket["id"]] = body
            client_reply[ticket["id"]] = gateway.reply(body)

        def reply_view(tid: str) -> dict:
            direct = client_reply[tid]
            if direct["http_status"] != 200:
                return direct
            edge_reply = out("reply", "gateway-http", tid)
            assert edge_reply == direct["body"], f"Edge and direct gateway reply differ for {tid}"
            return {"http_status": 200, "body": edge_reply}

        by_id = {t["id"]: t for t in all_tickets}
        http_io = {
            "read": {
                tid: {
                    "input": {"file": "data/events.jsonl"},
                    "output": out("raw", "gateway-http", tid),
                }
                for tid in ids
            },
            "parse": {
                tid: {
                    "input": out("raw", "gateway-http", tid),
                    "output": out("parsed", "gateway-http", tid),
                }
                for tid in ids
            },
            "request": {
                tid: {
                    "input": out("parsed", "gateway-http", tid),
                    "output": out("request", "gateway-http", tid),
                }
                for tid in ids
            },
            "reply": {
                tid: {"input": out("request", "gateway-http", tid), "output": reply_view(tid)}
                for tid in ids
            },
            "merge": {
                tid: {
                    "input": reply_view(tid)["body"],
                    "output": out("asked", "gateway-http", tid),
                }
                for tid in ids
            },
            "catch": {
                tid: {
                    "input": out("asked", "gateway-http", tid),
                    "output": out("caught", "gateway-http", tid),
                }
                for tid in ids
            },
            "output": {
                tid: {
                    "input": out("caught", "gateway-http", tid),
                    "output": out("caught", "gateway-http", tid),
                }
                for tid in ids
            },
        }
        sub_io = {
            "read": http_io["read"],
            "request": {tid: {"input": by_id[tid], "output": client_request[tid]} for tid in ids},
            "reply": {
                tid: {"input": client_request[tid], "output": reply_view(tid)} for tid in ids
            },
            "record": {
                tid: {
                    "input": reply_view(tid)["body"],
                    "output": out("client", "gateway-subprocess", tid),
                }
                for tid in ids
            },
            "output": {
                tid: {
                    "input": out("client", "gateway-subprocess", tid),
                    "output": out("client", "gateway-subprocess", tid),
                }
                for tid in ids
            },
        }

    for table in (http_io, sub_io):
        for entries in table.values():
            for entry in entries.values():
                for side in ("input", "output"):
                    entry[side] = public_view(entry[side])

    http_path = {
        "id": "gateway-http",
        "title": "HTTP in the pipeline",
        "pipeline": HTTP,
        "yaml": (ROOT / HTTP).read_text(),
        "summary": (
            "The pipeline builds the gateway request itself with a branch, "
            "so there is no child process."
        ),
        "stages": [
            stage(
                "read",
                "Read the ticket",
                "input: tickets (file)",
                "The file input emits one message per line of data/events.jsonl.",
                excerpt(HTTP, "input:"),
                http_io["read"],
            ),
            stage(
                "parse",
                "Parse the line",
                "mapping: parse_ticket",
                "The text line becomes a structured message, so later stages read its fields.",
                processor_block(HTTP, "parse_ticket"),
                http_io["parse"],
            ),
            stage(
                "request",
                "Build the request",
                "branch: ask_gateway, request_map",
                "The request map writes the ticket text, the classification instruction and "
                "the fixture name into the body sent to the gateway.",
                block_between(HTTP, "request_map:", "processors:"),
                http_io["request"],
            ),
            stage(
                "reply",
                "Ask the gateway",
                "branch: ask_gateway, http",
                "One POST to the node-local gateway. It retries for up to ten seconds, "
                "which covers the gateway starting after the pipeline. A ticket with no "
                "recorded answer returns 404 and is not retried.",
                block_between(HTTP, "- http:", "result_map:"),
                http_io["reply"],
            ),
            stage(
                "merge",
                "Merge the answer",
                "branch: ask_gateway, result_map",
                "The result map parses the answer text and adds category, sentiment and "
                "priority to the original ticket, plus where the answer came from.",
                block_between(HTTP, "result_map:", "- label: record_failure"),
                http_io["merge"],
            ),
            stage(
                "catch",
                "Record a failure",
                "catch: record_failure",
                "Only runs when an earlier stage failed. It replaces the message with an "
                "error record carrying the reason and writes a WARN line. Select ticket "
                "T-900 to see it run.",
                processor_block(HTTP, "record_failure"),
                http_io["catch"],
            ),
            stage(
                "log",
                "Log the result",
                "log: log_result",
                "One INFO line per ticket for the Logs view in Expanso Cloud. The message "
                "is not changed.",
                processor_block(HTTP, "log_result"),
                http_io["output"],
            ),
            stage(
                "output",
                "Write the record",
                "output: classified (stdout)",
                "The classified record leaves as one JSON line on stdout.",
                excerpt(HTTP, "output:"),
                http_io["output"],
            ),
        ],
    }
    sub_path = {
        "id": "gateway-subprocess",
        "title": "A Python client under the subprocess processor",
        "pipeline": SUB,
        "yaml": (ROOT / SUB).read_text(),
        "summary": (
            "One long-lived Python process reads tickets on stdin and writes records on "
            "stdout. Use it when request validation or response parsing belongs in code."
        ),
        "stages": [
            stage(
                "read",
                "Read the ticket",
                "input: tickets (file)",
                "The file input emits one message per line of data/events.jsonl.",
                excerpt(SUB, "input:"),
                sub_io["read"],
            ),
            stage(
                "request",
                "Build the request",
                "subprocess: classify_client, build_request",
                "The client turns the ticket into the request body for the gateway.",
                inspect.getsource(gateway_classify.build_request).rstrip(),
                sub_io["request"],
            ),
            stage(
                "reply",
                "Ask the gateway",
                "subprocess: classify_client, ask_gateway",
                "One POST to the node-local gateway. A refusal is raised with the "
                "gateway's own reason.",
                inspect.getsource(gateway_classify.ask_gateway).rstrip(),
                sub_io["reply"],
            ),
            stage(
                "record",
                "Validate and emit",
                "subprocess: classify_client",
                "The client checks each field against its allowed values, then prints one "
                "record per ticket. A bad ticket becomes an error record and the "
                "process keeps running.",
                processor_block(SUB, "classify_client"),
                sub_io["record"],
            ),
            stage(
                "log",
                "Log the result",
                "log: log_result",
                "One INFO line per ticket for the Logs view in Expanso Cloud. The message "
                "is not changed.",
                processor_block(SUB, "log_result"),
                sub_io["output"],
            ),
            stage(
                "output",
                "Write the record",
                "output: classified (stdout)",
                "The classified record leaves as one JSON line on stdout.",
                excerpt(SUB, "output:"),
                sub_io["output"],
            ),
        ],
    }
    return {
        "schema": 1,
        "tickets": [
            {
                "id": t["id"],
                "message": t["message"],
                "kind": "recorded" if t["id"] != FAILURE["id"] else "no recorded answer",
            }
            for t in all_tickets
        ],
        "omitted_gateway_fields": ["backend", "model", "recorded_at"],
        "paths": [http_path, sub_path],
    }


def stage_fixtures(contract: dict) -> dict[Path, str]:
    """One JSON Lines input file and one output file per stage, a line per
    ticket in the order the explorer lists them. Records each stage's
    fixtures and its published selector id on the stage."""
    files: dict[Path, str] = {}
    ticket_ids = [t["id"] for t in contract["tickets"]]
    for path in contract["paths"]:
        for index, item in enumerate(path["stages"], 1):
            stem = f"fixtures/stages/{path['id']}/{index:02d}-{item['id']}"
            item["data_stage"] = f"{path['id']}.{item['id']}"
            item["fixtures"] = {"input": f"{stem}.input.jsonl", "output": f"{stem}.output.jsonl"}
            for side in ("input", "output"):
                lines = [json.dumps(item["io"][t][side], ensure_ascii=False) for t in ticket_ids]
                files[ROOT / item["fixtures"][side]] = "\n".join(lines) + "\n"
    return files


def public_view(value):
    """Gateway replies also carry backend, model and recorded_at metadata that
    no pipeline reads. The explorer omits those three fields."""
    if isinstance(value, dict):
        return {
            k: public_view(v)
            for k, v in value.items()
            if k not in ("backend", "model", "recorded_at")
        }
    return value


# ------------------------------------------------------------------ proof run


def expected(name: str) -> dict[str, dict]:
    lines = (ROOT / "expected" / f"{name}.jsonl").read_text().splitlines()
    return {r["id"]: r for r in map(json.loads, lines)}


def prove_pipelines() -> list[dict]:
    rows = []
    for name in ("gateway-http", "gateway-subprocess"):
        started = time.monotonic()
        records, output, code = run_pipeline(f"pipelines/{name}.yaml", expect=4)
        elapsed = time.monotonic() - started
        got = {r["id"]: r for r in map(json.loads, records)}
        duration = re.search(r"Pipeline completed .*?duration=(\S+)", output)
        noisy = [line for line in output.splitlines() if " WRN " in line or " ERR " in line]
        rows.append(
            {
                "pipeline": name,
                "exit": code,
                "records": len(got),
                "match": got == expected(name),
                "noisy_lines": len(noisy),
                "digest": hashlib.sha256(
                    "".join(json.dumps(got[k], sort_keys=True) + "\n" for k in sorted(got)).encode()
                ).hexdigest(),
                "pipeline_duration": duration.group(1) if duration else "not reported",
                "wall_seconds": round(elapsed, 1),
            }
        )
    return rows


def prove_failure() -> list[dict]:
    rows = []
    with tempfile.TemporaryDirectory(prefix="agents-sdk-failure-") as tmp:
        workdir = Path(tmp)
        workdir.chmod(0o755)
        for name in ("gateway-http", "gateway-subprocess"):
            doc = load_pipeline(name)
            doc.pop("selector", None)
            record = edge_message(name, doc, FAILURE, workdir)
            rows.append({"pipeline": name, "record": record})
    return rows


def prove_node() -> dict:
    compose = [
        "docker",
        "compose",
        "-p",
        "agents-sdk-prove-node",
        "-f",
        "deploy/docker-compose.node.yaml",
    ]
    edge = "agents-sdk-prove-node-edge"
    try:
        sh(*compose, "up", "-d", "--build", "gateway", cwd=ROOT)
        sh(
            *compose,
            "run",
            "-d",
            "--name",
            edge,
            "--no-deps",
            "edge",
            "run",
            "--local",
            "--no-watch",
            "--config=/opt/demo/config/edge-node.yaml",
            "--data-dir=/tmp/edge",
            cwd=ROOT,
        )
        time.sleep(4)
        sh("docker", "exec", edge, "expanso-cli", "job", "deploy", "pipelines/gateway-http.yaml")
        time.sleep(3)
        logs = sh("docker", "logs", edge).stdout
        records = [line for line in logs.splitlines() if line.startswith("{")]
        status = json.loads(
            sh("docker", "exec", edge, "curl", "-fsS", "http://127.0.0.1:18157/status").stdout
        )
        inspected = json.loads(sh("docker", "inspect", edge).stdout)[0]["HostConfig"]
        return {
            "records": len(records),
            "gateway_fixture_calls": status["calls"]["fixture"],
            "gateway_live_calls": status["live_calls"],
            "network_mode": inspected["NetworkMode"].split(":")[0],
            "read_only_root": inspected["ReadonlyRootfs"],
            "capabilities_dropped": inspected["CapDrop"],
        }
    finally:
        subprocess.run(["docker", "rm", "-f", edge], capture_output=True, check=False)
        subprocess.run(
            [*compose, "--profile", "enroll", "down", "-v", "--remove-orphans"],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )


def versions() -> dict[str, str]:
    probe = sh(
        "docker",
        "run",
        "--rm",
        "--entrypoint",
        "sh",
        IMAGE,
        "-c",
        "expanso-edge version; expanso-cli version; python3 --version",
    )
    edge, cli, python = (probe.stdout.strip().splitlines() + ["", "", ""])[:3]
    return {"expanso-edge": edge, "expanso-cli": cli, "python": python}


def revision() -> str:
    head = sh("git", "rev-parse", "--short=12", "HEAD", cwd=ROOT).stdout.strip()
    dirty = sh(
        "git",
        "status",
        "--porcelain",
        "--",
        ".",
        ":!reports",
        ":!pipelines/explorer.json",
        ":!explorer",
        cwd=ROOT,
    ).stdout.strip()
    return head + (" with uncommitted changes" if dirty else "")


def write_report(rows: list[dict], failures: list[dict], node: dict | None, today: str) -> Path:
    tool = versions()
    lines = [
        f"# Run report, {today}",
        "",
        "Both published pipelines ran in the runner image on the shipped tickets, "
        "against the replay gateway. No model was called.",
        "",
        f"- Code revision: `{revision()}`",
        f"- Expanso Edge: `{tool['expanso-edge']}`, Expanso CLI: `{tool['expanso-cli']}`, "
        f"{tool['python']}",
        f"- Input: `data/events.jsonl`, sha256 `{sha256(ROOT / 'data' / 'events.jsonl')}`",
        f"- Fixtures: {len(list((ROOT / 'fixtures' / 'model').glob('*.json')))} recorded "
        "answers, zero live calls",
        "",
        "## Result",
        "",
        "| Pipeline | Exit | Records | Matches `expected/` | Warnings or errors | "
        "Pipeline duration | Output sha256 |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['pipeline']}` | {row['exit']} | {row['records']} of 4 | "
            f"{'yes' if row['match'] else 'NO'} | {row['noisy_lines']} | "
            f"{row['pipeline_duration']} | `{row['digest'][:16]}` |"
        )
    lines += [
        "",
        "The container stops itself once the fourth record appears and exits 0. "
        "A clean stop shows no warning or error line from Edge or the subprocess.",
        "",
        "## Failure record",
        "",
        f"Ticket `{FAILURE['id']}` has no recorded answer. Each pipeline returned this "
        "record, and the gateway refused instead of inventing an answer:",
        "",
    ]
    for item in failures:
        lines += [
            f"`{item['pipeline']}`",
            "",
            "```json",
            json.dumps(item["record"], indent=2),
            "```",
            "",
        ]
    if node is not None:
        lines += [
            "## Cloud node stack",
            "",
            "`deploy/docker-compose.node.yaml` was started in local mode (no Cloud "
            "credentials are used here). The pipeline reached the gateway that shares "
            "its network namespace:",
            "",
            f"- Records emitted: {node['records']}",
            f"- Gateway replayed {node['gateway_fixture_calls']} answers and made "
            f"{node['gateway_live_calls']} live calls",
            f"- Edge network mode: `{node['network_mode']}`; read-only root: "
            f"{node['read_only_root']}; capabilities dropped: {node['capabilities_dropped']}",
            "",
            "Enrolling the node in Expanso Cloud needs a bootstrap token and is not "
            "part of this run.",
            "",
        ]
    path = ROOT / "reports" / f"{today}-run.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(lines))
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the contract drifted")
    parser.add_argument("--node", action="store_true", help="also prove the node stack")
    parser.add_argument("--today", default=date.today().isoformat())
    args = parser.parse_args()

    if shutil.which("docker") is None:
        # CI sets PROVE_REQUIRE_DOCKER so a runner without Docker fails there.
        message = "docker is not on PATH and the proof run needs it"
        if os.environ.get("PROVE_REQUIRE_DOCKER"):
            print(f"FAIL: {message}")
            return 1
        print(f"skipping: {message}", file=sys.stderr)
        return 0

    build_image()
    rows = prove_pipelines()
    for row in rows:
        print(row)
    bad = [r for r in rows if r["exit"] or r["records"] != 4 or not r["match"] or r["noisy_lines"]]
    if bad:
        print(f"FAIL: {[r['pipeline'] for r in bad]}")
        return 1

    contract = capture([*tickets(), FAILURE])
    generated = stage_fixtures(contract)
    generated[CONTRACT] = json.dumps(contract, indent=2, ensure_ascii=False) + "\n"
    failures = prove_failure()
    for item in failures:
        if item["record"].get("_gateway_source") != "error":
            print(f"FAIL: {item['pipeline']} did not return an error record for {FAILURE['id']}")
            return 1
    if args.check:
        stale = [
            str(path.relative_to(ROOT))
            for path, text in generated.items()
            if not path.exists() or path.read_text() != text
        ]
        if stale:
            print(f"FAIL: differs from a fresh run: {stale}")
            return 1
        print(f"explorer contract and {len(generated) - 1} stage fixtures match a fresh run")
    else:
        for path, text in generated.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    node = prove_node() if args.node else None
    path = write_report(rows, failures, node, args.today)
    print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
