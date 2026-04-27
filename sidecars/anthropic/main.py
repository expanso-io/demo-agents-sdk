"""Anthropic SDK sidecar — classifies support tickets."""

# /// script
# requires-python = ">=3.11"
# dependencies = ["fastapi", "uvicorn[standard]", "anthropic>=0.40.0", "pydantic>=2"]
# ///
from __future__ import annotations

import json
import os
import re

from anthropic import Anthropic
from fastapi import FastAPI
from pydantic import BaseModel

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
SYSTEM = (
    "Classify support tickets. Respond with strict JSON only, no prose: "
    '{"category":"billing|technical|account|other",'
    '"sentiment":"pos|neg|neu",'
    '"priority":"low|med|high"}'
)

app = FastAPI()
client = Anthropic()


class Ticket(BaseModel):
    id: str
    message: str


class Classification(BaseModel):
    id: str
    category: str
    sentiment: str
    priority: str


def extract_json(text: str) -> dict:
    """Anthropic doesn't have a json_object response_format flag; the model
    occasionally wraps JSON in prose. Pull the first {...} block."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in response: {text!r}")
    return json.loads(match.group(0))


@app.post("/classify", response_model=Classification)
def classify(ticket: Ticket) -> Classification:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=200,
        system=SYSTEM,
        messages=[{"role": "user", "content": ticket.message}],
    )
    text = resp.content[0].text  # type: ignore[union-attr]
    parsed = extract_json(text)
    return Classification(id=ticket.id, **parsed)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "model": MODEL}
