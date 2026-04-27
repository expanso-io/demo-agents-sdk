"""Gemini SDK sidecar — classifies support tickets."""

# /// script
# requires-python = ">=3.11"
# dependencies = ["fastapi", "uvicorn[standard]", "google-genai>=0.3.0", "pydantic>=2"]
# ///
from __future__ import annotations

import os

from fastapi import FastAPI
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

app = FastAPI()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


class Ticket(BaseModel):
    id: str
    message: str


class Classification(BaseModel):
    id: str
    category: str
    sentiment: str
    priority: str


class _LLMOut(BaseModel):
    category: str
    sentiment: str
    priority: str


@app.post("/classify", response_model=Classification)
def classify(ticket: Ticket) -> Classification:
    resp = client.models.generate_content(
        model=MODEL,
        contents=ticket.message,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM,
            response_mime_type="application/json",
            response_schema=_LLMOut,
        ),
    )
    parsed: _LLMOut = resp.parsed  # type: ignore[assignment]
    return Classification(
        id=ticket.id,
        category=parsed.category,
        sentiment=parsed.sentiment,
        priority=parsed.priority,
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "model": MODEL}
