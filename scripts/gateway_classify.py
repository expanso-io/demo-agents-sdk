#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Classify support tickets through the demo-kit model gateway."""

from __future__ import annotations

import json
import os
import signal
import sys
import urllib.error
import urllib.request

GATEWAY_URL = os.environ.get("MODEL_GATEWAY_URL", "http://127.0.0.1:18157/ask")
SYSTEM = (
    "Classify this support ticket. Respond with strict JSON only, no prose: "
    '{"category":"billing|technical|account|other",'
    '"sentiment":"pos|neg|neu",'
    '"priority":"low|med|high"}'
)
VALID = {
    "category": {"billing", "technical", "account", "other"},
    "sentiment": {"pos", "neg", "neu"},
    "priority": {"low", "med", "high"},
}


def build_request(message: str, fixture: str) -> dict[str, str]:
    return {"prompt": message, "system": SYSTEM, "fixture": fixture}


def ask_gateway(message: str, fixture: str) -> dict:
    request = urllib.request.Request(
        GATEWAY_URL,
        data=json.dumps(build_request(message, fixture)).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=250) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = json.loads(error.read() or b"{}")
        raise RuntimeError(detail.get("reason", f"gateway returned {error.code}")) from None


def classify(message: str, fixture: str) -> tuple[dict[str, str], str]:
    gateway = ask_gateway(message, fixture)
    parsed = json.loads(gateway["text"])
    for field, allowed in VALID.items():
        if parsed.get(field) not in allowed:
            raise ValueError(f"gateway returned invalid {field}: {parsed.get(field)!r}")
    return parsed, gateway["source"]


def main() -> None:
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    for raw_line in sys.stdin:
        if not (line := raw_line.strip()):
            continue
        ticket_id = "?"
        try:
            ticket = json.loads(line)
            ticket_id = str(ticket["id"])
            result, source = classify(
                str(ticket["message"]),
                f"support-{ticket_id}",
            )
            out = {
                "id": ticket_id,
                **result,
                "_gateway_source": source,
                "_mode": "subprocess",
            }
        except Exception as error:
            out = {
                "id": ticket_id,
                "error": f"{type(error).__name__}: {error}",
                "_gateway_source": "error",
                "_mode": "subprocess",
            }
        try:
            print(json.dumps(out), flush=True)
        except BrokenPipeError:
            # Edge closed our stdout while stopping: nothing is left to deliver.
            return


if __name__ == "__main__":
    main()
