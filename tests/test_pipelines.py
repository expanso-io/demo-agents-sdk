"""Structural tests for the two model-gateway pipeline integrations."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

PIPELINES_DIR = Path(__file__).parent.parent / "pipelines"
ALL_PIPELINES = sorted(PIPELINES_DIR.glob("*.yaml"))


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _seconds(value: str) -> int:
    assert value.endswith("s")
    return int(value[:-1])


def test_only_gateway_pipelines_exist():
    assert {path.stem for path in ALL_PIPELINES} == {
        "gateway-http",
        "gateway-subprocess",
    }


@pytest.mark.parametrize("path", ALL_PIPELINES, ids=lambda path: path.name)
def test_shared_input_and_output(path):
    config = _load(path)["config"]
    assert config["input"]["file"] == {
        "paths": ["data/events.jsonl"],
        "codec": "lines",
    }
    assert config["output"]["stdout"]["codec"] == "lines"


def test_http_pipeline_targets_only_local_gateway():
    processors = _load(PIPELINES_DIR / "gateway-http.yaml")["config"]["pipeline"]["processors"]
    branch = next(processor["branch"] for processor in processors if "branch" in processor)
    http = next(processor["http"] for processor in branch["processors"] if "http" in processor)
    assert http["url"] == "http://127.0.0.1:18157/ask"
    assert http["retries"] >= 1
    assert http["retries"] * _seconds(http["retry_period"]) >= 5
    assert set(http["headers"]) == {"Content-Type"}
    assert "root.category = $parsed.category" in branch["result_map"]


def test_subprocess_pipeline_uses_gateway_client():
    processors = _load(PIPELINES_DIR / "gateway-subprocess.yaml")["config"]["pipeline"][
        "processors"
    ]
    subprocess = processors[0]["subprocess"]
    assert subprocess == {
        "name": "python3",
        "args": ["scripts/gateway_classify.py"],
    }
