"""Unit tests for scripts/openai_classify.py.

Mocks the OpenAI client so no network calls happen and no real API key is
needed. Verifies: classify() request shape, response parsing, main() loop IO,
empty-line handling, and graceful error handling on both bad input and SDK
failures.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import openai_classify  # noqa: E402  (sys.path setup happens in conftest)


def _fake_response(json_payload: str) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = json_payload
    return resp


def test_classify_returns_parsed_json():
    fake = _fake_response('{"category":"billing","sentiment":"neg","priority":"high"}')
    with patch.object(openai_classify, "client") as mc:
        mc.chat.completions.create.return_value = fake
        result = openai_classify.classify("I was double-charged")
    assert result == {"category": "billing", "sentiment": "neg", "priority": "high"}


def test_classify_passes_response_format_json_object():
    fake = _fake_response("{}")
    with patch.object(openai_classify, "client") as mc:
        mc.chat.completions.create.return_value = fake
        openai_classify.classify("hello")
    kwargs = mc.chat.completions.create.call_args.kwargs
    assert kwargs["response_format"] == {"type": "json_object"}


def test_classify_includes_system_and_user_messages():
    fake = _fake_response("{}")
    with patch.object(openai_classify, "client") as mc:
        mc.chat.completions.create.return_value = fake
        openai_classify.classify("ticket text")
    msgs = mc.chat.completions.create.call_args.kwargs["messages"]
    assert msgs[0]["role"] == "system"
    assert "Classify support tickets" in msgs[0]["content"]
    assert msgs[1] == {"role": "user", "content": "ticket text"}


def test_classify_uses_model_from_env(monkeypatch):
    # Module-level MODEL was already captured at import; verify the call uses it.
    fake = _fake_response("{}")
    with patch.object(openai_classify, "client") as mc:
        mc.chat.completions.create.return_value = fake
        openai_classify.classify("x")
    assert mc.chat.completions.create.call_args.kwargs["model"] == openai_classify.MODEL


def test_main_emits_classified_jsonl(monkeypatch, capsys):
    fake = _fake_response('{"category":"technical","sentiment":"neg","priority":"high"}')
    monkeypatch.setattr("sys.stdin", io.StringIO('{"id":"T-001","message":"prod down"}\n'))
    with patch.object(openai_classify, "client") as mc:
        mc.chat.completions.create.return_value = fake
        openai_classify.main()
    out = capsys.readouterr().out.strip()
    parsed = json.loads(out)
    assert parsed == {
        "id": "T-001",
        "category": "technical",
        "sentiment": "neg",
        "priority": "high",
        "_provider": "openai",
        "_mode": "subprocess",
    }


def test_main_skips_blank_lines(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("\n   \n\n"))
    openai_classify.main()
    assert capsys.readouterr().out == ""


def test_main_emits_error_row_on_bad_json(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("not valid json\n"))
    openai_classify.main()
    parsed = json.loads(capsys.readouterr().out.strip())
    assert "error" in parsed
    assert parsed["_provider"] == "openai"
    assert parsed["_mode"] == "subprocess"


def test_main_emits_error_row_on_sdk_failure(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO('{"id":"T-001","message":"x"}\n'))
    with patch.object(openai_classify, "client") as mc:
        mc.chat.completions.create.side_effect = RuntimeError("upstream timeout")
        openai_classify.main()
    parsed = json.loads(capsys.readouterr().out.strip())
    assert "RuntimeError" in parsed["error"]
    assert "upstream timeout" in parsed["error"]


def test_main_processes_multiple_lines(monkeypatch, capsys):
    fake = _fake_response('{"category":"billing","sentiment":"neg","priority":"med"}')
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            '{"id":"A","message":"m1"}\n{"id":"B","message":"m2"}\n{"id":"C","message":"m3"}\n'
        ),
    )
    with patch.object(openai_classify, "client") as mc:
        mc.chat.completions.create.return_value = fake
        openai_classify.main()
    lines = [line for line in capsys.readouterr().out.splitlines() if line]
    assert len(lines) == 3
    ids = [json.loads(line)["id"] for line in lines]
    assert ids == ["A", "B", "C"]


def test_print_uses_flush_true():
    """Critical for Expanso subprocess processor — without flush=True the
    pipeline hangs waiting on Python's stdout buffer."""
    source = Path(openai_classify.__file__).read_text()
    assert "flush=True" in source, "main() must print with flush=True"
