#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.11"
# dependencies = ["anthropic>=0.40.0"]
# ///
"""Classify support tickets using Anthropic. Reads JSONL from stdin, writes
JSONL to stdout. Long-lived under Expanso's `subprocess` processor.

Anthropic doesn't have a `json_object` response_format flag — we extract the
first {...} block from the model's text output instead.
"""

from __future__ import annotations

import json
import os
import re
import sys

from anthropic import Anthropic

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
SYSTEM = (
    "Classify support tickets. Respond with strict JSON only, no prose: "
    '{"category":"billing|technical|account|other",'
    '"sentiment":"pos|neg|neu",'
    '"priority":"low|med|high"}'
)

client = Anthropic()


def classify(message: str) -> dict:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=200,
        system=SYSTEM,
        messages=[{"role": "user", "content": message}],
    )
    text = resp.content[0].text  # type: ignore[union-attr]
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in response: {text!r}")
    return json.loads(match.group(0))


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            ticket = json.loads(line)
            out = {
                "id": ticket["id"],
                **classify(ticket["message"]),
                "_provider": "anthropic",
                "_mode": "subprocess",
            }
        except Exception as e:
            out = {
                "id": "?",
                "error": f"{type(e).__name__}: {e}",
                "_provider": "anthropic",
                "_mode": "subprocess",
            }
        print(json.dumps(out), flush=True)


if __name__ == "__main__":
    main()
