"""OpenAI SDK sidecar — classifies support tickets."""

# /// script
# requires-python = ">=3.11"
# dependencies = ["fastapi", "uvicorn[standard]", "openai>=1.50.0", "pydantic>=2"]
# ///
from __future__ import annotations

import json
import os

from fastapi import FastAPI
from openai import OpenAI
from pydantic import BaseModel

MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
SYSTEM = (
    "Classify support tickets. Respond with strict JSON: "
    '{"category":"billing|technical|account|other",'
    '"sentiment":"pos|neg|neu",'
    '"priority":"low|med|high"}'
)

app = FastAPI()
client = OpenAI()


class Ticket(BaseModel):
    id: str
    message: str


class Classification(BaseModel):
    id: str
    category: str
    sentiment: str
    priority: str


@app.post("/classify", response_model=Classification)
def classify(ticket: Ticket) -> Classification:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": ticket.message},
        ],
        response_format={"type": "json_object"},
    )
    parsed = json.loads(resp.choices[0].message.content or "{}")
    return Classification(id=ticket.id, **parsed)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "model": MODEL}
