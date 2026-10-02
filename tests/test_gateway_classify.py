"""Unit tests for the long-lived model gateway client."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import gateway_classify
import pytest


def _response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    return response


def test_classify_posts_prompt_system_and_fixture():
    payload = {
        "text": '{"category":"billing","sentiment":"neg","priority":"high"}',
        "source": "fixture",
    }
    with patch.object(gateway_classify.urllib.request, "urlopen", return_value=_response(payload)):
        result, source = gateway_classify.classify("charged twice", "support-T-001")
    assert result == {"category": "billing", "sentiment": "neg", "priority": "high"}
    assert source == "fixture"


def test_classify_rejects_invalid_schema():
    payload = {
        "text": '{"category":"sales","sentiment":"neg","priority":"high"}',
        "source": "fixture",
    }
    with (
        patch.object(gateway_classify.urllib.request, "urlopen", return_value=_response(payload)),
        pytest.raises(ValueError, match="invalid category"),
    ):
        gateway_classify.classify("buy", "support-T-002")


def test_main_emits_classified_jsonl(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO('{"id":"T-001","message":"refund"}\n'))
    result = {"category": "billing", "sentiment": "neg", "priority": "high"}
    with patch.object(gateway_classify, "classify", return_value=(result, "fixture")) as call:
        gateway_classify.main()
    assert json.loads(capsys.readouterr().out) == {
        "id": "T-001",
        **result,
        "_gateway_source": "fixture",
        "_mode": "subprocess",
    }
    call.assert_called_once_with("refund", "support-T-001")


def test_main_emits_error_without_stopping(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("bad json\n"))
    gateway_classify.main()
    output = json.loads(capsys.readouterr().out)
    assert output["id"] == "?"
    assert "JSONDecodeError" in output["error"]
    assert output["_gateway_source"] == "error"


def test_print_uses_flush_true():
    source = Path(gateway_classify.__file__).read_text()
    assert "flush=True" in source
