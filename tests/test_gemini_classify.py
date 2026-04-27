"""Unit tests for scripts/gemini_classify.py.

Gemini uses a typed `response_schema` for structured output — `resp.parsed`
returns a Pydantic model instance, not a string. The tests below verify both
the schema is wired correctly and the parsed model is converted to a dict
matching the shared output schema.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import gemini_classify  # noqa: E402


def _fake_response(category: str, sentiment: str, priority: str) -> MagicMock:
    resp = MagicMock()
    resp.parsed = gemini_classify._LLMOut(category=category, sentiment=sentiment, priority=priority)
    return resp


def test_classify_returns_parsed_dict():
    fake = _fake_response("billing", "neg", "high")
    with patch.object(gemini_classify, "client") as mc:
        mc.models.generate_content.return_value = fake
        result = gemini_classify.classify("I was double-charged")
    assert result == {"category": "billing", "sentiment": "neg", "priority": "high"}


def test_classify_uses_response_mime_type_json():
    fake = _fake_response("other", "neu", "low")
    with patch.object(gemini_classify, "client") as mc:
        mc.models.generate_content.return_value = fake
        gemini_classify.classify("hi")
    config = mc.models.generate_content.call_args.kwargs["config"]
    assert config.response_mime_type == "application/json"


def test_classify_passes_response_schema_class():
    fake = _fake_response("other", "neu", "low")
    with patch.object(gemini_classify, "client") as mc:
        mc.models.generate_content.return_value = fake
        gemini_classify.classify("hi")
    config = mc.models.generate_content.call_args.kwargs["config"]
    assert config.response_schema is gemini_classify._LLMOut


def test_classify_passes_system_instruction():
    fake = _fake_response("other", "neu", "low")
    with patch.object(gemini_classify, "client") as mc:
        mc.models.generate_content.return_value = fake
        gemini_classify.classify("hi")
    config = mc.models.generate_content.call_args.kwargs["config"]
    assert "Classify support tickets" in config.system_instruction


def test_classify_passes_message_as_contents():
    fake = _fake_response("other", "neu", "low")
    with patch.object(gemini_classify, "client") as mc:
        mc.models.generate_content.return_value = fake
        gemini_classify.classify("the message body")
    assert mc.models.generate_content.call_args.kwargs["contents"] == "the message body"


def test_main_emits_classified_jsonl(monkeypatch, capsys):
    fake = _fake_response("technical", "neg", "high")
    monkeypatch.setattr("sys.stdin", io.StringIO('{"id":"T-002","message":"500 error"}\n'))
    with patch.object(gemini_classify, "client") as mc:
        mc.models.generate_content.return_value = fake
        gemini_classify.main()
    parsed = json.loads(capsys.readouterr().out.strip())
    assert parsed == {
        "id": "T-002",
        "category": "technical",
        "sentiment": "neg",
        "priority": "high",
        "_provider": "gemini",
        "_mode": "subprocess",
    }


def test_main_emits_error_row_on_sdk_failure(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO('{"id":"T-001","message":"x"}\n'))
    with patch.object(gemini_classify, "client") as mc:
        mc.models.generate_content.side_effect = TimeoutError("deadline exceeded")
        gemini_classify.main()
    parsed = json.loads(capsys.readouterr().out.strip())
    assert "TimeoutError" in parsed["error"]


def test_print_uses_flush_true():
    source = Path(gemini_classify.__file__).read_text()
    assert "flush=True" in source
