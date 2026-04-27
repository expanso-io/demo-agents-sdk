#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Zero-dependency stub classifier for the E2E smoke test.

Reads JSONL from stdin and emits deterministic fake classifications to
stdout. Same IO contract as the real classifiers in scripts/, but no SDK
import, no network call, no API key required. Used by tests/test_smoke.py to
prove that the runner image, uv installation, subprocess processor, and
pipeline IO all wire up correctly without burning any LLM tokens.

Invoked via `uv run -s` (matches the real SDK pipelines) so we exercise the
same execution path. Empty dependency list — uv only spins up a Python
interpreter, no package install required.
"""

from __future__ import annotations

import json
import sys


def fake_classification(message: str) -> dict:
    # Deterministic mock derived from the message — enough for tests to
    # verify that input flows all the way through to output.
    text = message.lower()
    if any(word in text for word in ("charge", "refund", "billing", "subscription")):
        category = "billing"
    elif any(word in text for word in ("urgent", "down", "error", "broken")):
        category = "technical"
    elif any(word in text for word in ("user", "password", "account")):
        category = "account"
    else:
        category = "other"
    return {
        "category": category,
        "sentiment": "neg" if "urgent" in text or "error" in text else "neu",
        "priority": "high" if "urgent" in text else "low",
    }


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            ticket = json.loads(line)
            out = {
                "id": ticket["id"],
                **fake_classification(ticket["message"]),
                "_provider": "stub",
                "_mode": "subprocess",
            }
        except Exception as e:
            out = {
                "id": "?",
                "error": f"{type(e).__name__}: {e}",
                "_provider": "stub",
                "_mode": "subprocess",
            }
        print(json.dumps(out), flush=True)


if __name__ == "__main__":
    main()
