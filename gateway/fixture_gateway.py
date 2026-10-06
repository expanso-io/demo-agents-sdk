#!/usr/bin/env python3
"""Replay-only model gateway for Expanso Edge nodes.

Serves the same two routes as the demo-kit model gateway, on 127.0.0.1 only:

    POST /ask     {"prompt": "...", "system": "...", "fixture": "name"}
    GET  /status  call counters and the number of recorded answers

It has no live mode, no backend and no credential. An answer is found by the
SHA-256 of the whitespace-normalized system and prompt text, then by fixture
name, exactly as the demo-kit gateway does, so fixtures recorded there replay
here unchanged. Recording stays with the demo-kit gateway on the host.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_PROMPT = 400_000
DEFAULT_PORT = 18157
LOCAL_ORIGIN = re.compile(r"https?://(localhost|127\.0\.0\.1)(:\d+)?$")


def normalize(text: str) -> str:
    return " ".join((text or "").split())


def prompt_key(system: str, prompt: str) -> str:
    return hashlib.sha256(f"{normalize(system)}\x1e{normalize(prompt)}".encode()).hexdigest()


class Replay:
    def __init__(self, fixtures: Path) -> None:
        self.records: list[dict] = []
        for path in sorted(fixtures.glob("*.json")):
            try:
                self.records.append(json.loads(path.read_text()))
            except (OSError, ValueError):
                continue
        self.counts = {"fixture": 0, "no_fixture": 0, "bad_request": 0}
        self.lock = threading.Lock()

    def find(self, key: str, name: str) -> dict | None:
        by_name = None
        for record in self.records:
            if record.get("prompt_sha256") == key:
                return {**record, "match": "prompt"}
            if name and record.get("name") == name:
                by_name = {**record, "match": "name"}
        return by_name

    def ask(self, prompt: str, system: str, name: str) -> tuple[int, dict]:
        if not prompt.strip() or len(prompt) + len(system) > MAX_PROMPT:
            with self.lock:
                self.counts["bad_request"] += 1
            return 400, {"status": "bad_request", "reason": "empty or oversized prompt"}
        key = prompt_key(system, prompt)
        record = self.find(key, name)
        if record is None:
            with self.lock:
                self.counts["no_fixture"] += 1
            return 404, {
                "status": "no_fixture",
                "key": key,
                "reason": "fixture mode: no recorded answer for this prompt",
            }
        with self.lock:
            self.counts["fixture"] += 1
        return 200, {
            "status": "ok",
            "source": "fixture",
            "match": record["match"],
            "key": key,
            "text": record["text"],
            "backend": record.get("backend"),
            "model": record.get("model"),
            "recorded_at": record.get("recorded_at"),
        }

    def status(self) -> dict:
        return {
            "mode": "fixture",
            "recorded_answers": len(self.records),
            "calls": dict(self.counts),
            "live_calls": 0,
        }


def make_handler(replay: Replay) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def reply(self, code: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802 - http.server API
            if self.path == "/status":
                self.reply(200, replay.status())
            else:
                self.reply(404, {"status": "not_found"})

        def do_POST(self) -> None:  # noqa: N802 - http.server API
            if self.path != "/ask":
                self.reply(404, {"status": "not_found"})
                return
            if "application/json" not in self.headers.get("Content-Type", ""):
                self.reply(415, {"status": "bad_request", "reason": "send application/json"})
                return
            origin = self.headers.get("Origin", "")
            if origin and not LOCAL_ORIGIN.match(origin):
                self.reply(403, {"status": "refused", "reason": "foreign origin"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0") or 0)
                if length > MAX_PROMPT * 2:
                    self.reply(413, {"status": "bad_request", "reason": "body too large"})
                    return
                body = json.loads(self.rfile.read(length) or b"{}")
                prompt, system, name = (
                    str(body.get("prompt", "")),
                    str(body.get("system", "")),
                    str(body.get("fixture", "")),
                )
            except (ValueError, AttributeError):
                self.reply(400, {"status": "bad_request", "reason": "body is not JSON"})
                return
            self.reply(*replay.ask(prompt, system, name))

        def log_message(self, *args: object) -> None:
            return

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--fixtures",
        default=os.environ.get("FIXTURE_DIR", "fixtures/model"),
        help="directory of recorded answers (*.json)",
    )
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("GATEWAY_PORT", DEFAULT_PORT))
    )
    args = parser.parse_args()

    replay = Replay(Path(args.fixtures))
    if not replay.records:
        print(f"fixture-gateway: no recorded answers in {args.fixtures}", file=sys.stderr)
        return 2
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(replay))
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown).start())
    print(
        f"fixture-gateway: {len(replay.records)} recorded answers on 127.0.0.1:{args.port}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
