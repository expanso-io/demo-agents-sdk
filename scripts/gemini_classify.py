#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.11"
# dependencies = ["google-genai>=0.3.0", "pydantic>=2"]
# ///
"""Classify support tickets using Gemini. Reads JSONL from stdin, writes JSONL
to stdout. Long-lived under Expanso's `subprocess` processor.

Uses google-genai's `response_schema` for typed structured output instead of
prompt-driven JSON.
"""

from __future__ import annotations

import json
import os
import sys

from google import genai
from google.genai import types
from pydantic import BaseModel

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
SYSTEM = (
    "Classify support tickets. Respond with strict JSON: "
    '{"category":"billing|technical|account|other",'
    '"sentiment":"pos|neg|neu",'
    '"priority":"low|med|high"}'
)


class _LLMOut(BaseModel):
    category: str
    sentiment: str
    priority: str


client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def classify(message: str) -> dict:
    resp = client.models.generate_content(
        model=MODEL,
        contents=message,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM,
            response_mime_type="application/json",
            response_schema=_LLMOut,
        ),
    )
    parsed: _LLMOut = resp.parsed  # type: ignore[assignment]
    return parsed.model_dump()


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
                "_provider": "gemini",
                "_mode": "subprocess",
            }
        except Exception as e:
            out = {
                "id": "?",
                "error": f"{type(e).__name__}: {e}",
                "_provider": "gemini",
                "_mode": "subprocess",
            }
        print(json.dumps(out), flush=True)


if __name__ == "__main__":
    main()
