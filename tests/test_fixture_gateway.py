"""The replay gateway answers from the committed fixtures and nothing else."""

from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "gateway"))

import fixture_gateway  # noqa: E402
import gateway_classify  # noqa: E402


@pytest.fixture(scope="module")
def server():
    replay = fixture_gateway.Replay(ROOT / "fixtures" / "model")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), fixture_gateway.make_handler(replay))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", replay
    httpd.shutdown()
    httpd.server_close()


def _post(url: str, body: dict, headers: dict | None = None):
    request = urllib.request.Request(
        url + "/ask",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def _tickets() -> list[dict]:
    lines = (ROOT / "data" / "events.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines]


@pytest.mark.parametrize("ticket", _tickets(), ids=lambda t: t["id"])
def test_every_shipped_ticket_replays_by_prompt_hash(server, ticket):
    url, _ = server
    body = gateway_classify.build_request(ticket["message"], "support-" + ticket["id"])
    status, answer = _post(url, body)
    assert status == 200
    assert answer["source"] == "fixture"
    assert answer["match"] == "prompt"
    assert set(json.loads(answer["text"])) == {"category", "sentiment", "priority"}


def test_unknown_prompt_is_refused_never_invented(server):
    url, _ = server
    status, answer = _post(url, {"prompt": "never recorded", "system": "s"})
    assert status == 404
    assert answer["status"] == "no_fixture"


def test_foreign_origin_and_wrong_content_type_are_refused(server):
    url, _ = server
    status, _ = _post(url, {"prompt": "x"}, {"Origin": "https://example.com"})
    assert status == 403
    request = urllib.request.Request(
        url + "/ask", data=b"{}", headers={"Content-Type": "text/plain"}
    )
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request, timeout=5)
    assert error.value.code == 415


def test_status_reports_zero_live_calls(server):
    url, _ = server
    with urllib.request.urlopen(url + "/status", timeout=5) as response:
        status = json.loads(response.read())
    assert status["mode"] == "fixture"
    assert status["live_calls"] == 0
    assert status["recorded_answers"] == 4


def test_gateway_binds_loopback_only():
    source = (ROOT / "gateway" / "fixture_gateway.py").read_text()
    assert '("127.0.0.1", args.port)' in source
    assert "0.0.0.0" not in source
