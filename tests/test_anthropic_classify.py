"""Unit tests for scripts/anthropic_classify.py.

Anthropic doesn't expose a `json_object` response_format flag, so the script
extracts the first {...} block from the model's free-text output via regex.
That extraction is the most failure-prone part of this provider's
implementation — the tests below exercise it heavily.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import anthropic_classify  # noqa: E402
import pytest


def _fake_response(text: str) -> MagicMock:
    resp = MagicMock()
    block = MagicMock()
    block.text = text
    resp.content = [block]
    return resp


def test_classify_returns_parsed_json():
    fake = _fake_response('{"category":"billing","sentiment":"neg","priority":"high"}')
    with patch.object(anthropic_classify, "client") as mc:
        mc.messages.create.return_value = fake
        result = anthropic_classify.classify("test")
    assert result == {"category": "billing", "sentiment": "neg", "priority": "high"}


def test_classify_extracts_json_from_prose_wrapper():
    fake = _fake_response(
        "Sure! Here is the classification: "
        '{"category":"technical","sentiment":"neg","priority":"high"}'
        " — let me know if you want anything else."
    )
    with patch.object(anthropic_classify, "client") as mc:
        mc.messages.create.return_value = fake
        result = anthropic_classify.classify("test")
    assert result["category"] == "technical"


def test_classify_extracts_json_across_newlines():
    fake = _fake_response(
        'Here is the result:\n\n{\n  "category": "account",\n  '
        '"sentiment": "neu",\n  "priority": "low"\n}\n\nThanks.'
    )
    with patch.object(anthropic_classify, "client") as mc:
        mc.messages.create.return_value = fake
        result = anthropic_classify.classify("test")
    assert result["category"] == "account"


def test_classify_raises_when_no_json_present():
    fake = _fake_response("I cannot classify this ticket.")
    with patch.object(anthropic_classify, "client") as mc:
        mc.messages.create.return_value = fake
        with pytest.raises(ValueError, match="no JSON"):
            anthropic_classify.classify("test")


def test_classify_passes_system_via_system_param():
    fake = _fake_response('{"category":"other","sentiment":"neu","priority":"low"}')
    with patch.object(anthropic_classify, "client") as mc:
        mc.messages.create.return_value = fake
        anthropic_classify.classify("hi")
    kwargs = mc.messages.create.call_args.kwargs
    assert "Classify support tickets" in kwargs["system"]
    assert kwargs["messages"] == [{"role": "user", "content": "hi"}]
    assert kwargs["max_tokens"] == 200


def test_main_emits_classified_jsonl(monkeypatch, capsys):
    fake = _fake_response('{"category":"billing","sentiment":"neg","priority":"high"}')
    monkeypatch.setattr("sys.stdin", io.StringIO('{"id":"T-001","message":"refund"}\n'))
    with patch.object(anthropic_classify, "client") as mc:
        mc.messages.create.return_value = fake
        anthropic_classify.main()
    parsed = json.loads(capsys.readouterr().out.strip())
    assert parsed["id"] == "T-001"
    assert parsed["category"] == "billing"
    assert parsed["_provider"] == "anthropic"
    assert parsed["_mode"] == "subprocess"


def test_main_emits_error_row_on_unparseable_response(monkeypatch, capsys):
    fake = _fake_response("Sorry, I can't help with that.")
    monkeypatch.setattr("sys.stdin", io.StringIO('{"id":"T-001","message":"x"}\n'))
    with patch.object(anthropic_classify, "client") as mc:
        mc.messages.create.return_value = fake
        anthropic_classify.main()
    parsed = json.loads(capsys.readouterr().out.strip())
    assert "error" in parsed
    assert "ValueError" in parsed["error"]


def test_main_emits_error_row_on_sdk_failure(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO('{"id":"T-001","message":"x"}\n'))
    with patch.object(anthropic_classify, "client") as mc:
        mc.messages.create.side_effect = ConnectionError("network down")
        anthropic_classify.main()
    parsed = json.loads(capsys.readouterr().out.strip())
    assert "ConnectionError" in parsed["error"]


def test_print_uses_flush_true():
    source = Path(anthropic_classify.__file__).read_text()
    assert "flush=True" in source
