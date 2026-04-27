#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=1.50.0"]
# ///
"""Classify support tickets using OpenAI. Reads JSONL from stdin, writes JSONL
to stdout. Designed to run under the Expanso `subprocess` processor — the
process stays alive across messages, so the SDK is imported once, not per call.

Expanso requires every output line to be flushed; otherwise the pipeline hangs
waiting on Python's stdout buffer.
"""

from __future__ import annotations

import json
import os
import sys

from openai import OpenAI

MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
SYSTEM = (
    "Classify support tickets. Respond with strict JSON: "
    '{"category":"billing|technical|account|other",'
    '"sentiment":"pos|neg|neu",'
    '"priority":"low|med|high"}'
)

client = OpenAI()


def classify(message: str) -> dict:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": message},
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content or "{}")


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
                "_provider": "openai",
                "_mode": "subprocess",
            }
        except Exception as e:
            out = {
                "id": "?",
                "error": f"{type(e).__name__}: {e}",
                "_provider": "openai",
                "_mode": "subprocess",
            }
        print(json.dumps(out), flush=True)


if __name__ == "__main__":
    main()
