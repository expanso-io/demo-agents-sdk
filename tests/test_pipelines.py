"""Structural tests for pipelines/*.yaml.

These don't validate Bloblang or Expanso semantics — `expanso-cli job validate
--offline` (run separately) does that. These assert the cross-cutting shape
contracts the Python tests and compose layout depend on: each pipeline reads
the same input file, names match the filename, SDK pipelines wire to the
right script, HTTP pipelines hit the right endpoint host.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

PIPELINES_DIR = Path(__file__).parent.parent / "pipelines"
ALL_PIPELINES = sorted(PIPELINES_DIR.glob("*.yaml"))
SDK_PIPELINES = [p for p in ALL_PIPELINES if p.stem.endswith("-sdk")]
HTTP_PIPELINES = [p for p in ALL_PIPELINES if p.stem.endswith("-http")]

EXPECTED_HOSTS = {
    "openai-http": "api.openai.com",
    "anthropic-http": "api.anthropic.com",
    "gemini-http": "generativelanguage.googleapis.com",
}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def test_six_pipelines_exist():
    names = {p.stem for p in ALL_PIPELINES}
    assert names == {
        "openai-http",
        "openai-sdk",
        "anthropic-http",
        "anthropic-sdk",
        "gemini-http",
        "gemini-sdk",
    }


@pytest.mark.parametrize("path", ALL_PIPELINES, ids=lambda p: p.name)
def test_top_level_is_pipeline_resource(path):
    doc = _load(path)
    assert doc["type"] == "pipeline"
    assert doc["name"] == path.stem


@pytest.mark.parametrize("path", ALL_PIPELINES, ids=lambda p: p.name)
def test_input_reads_shared_jsonl(path):
    doc = _load(path)
    assert doc["config"]["input"]["file"]["paths"] == ["/data/events.jsonl"]
    assert doc["config"]["input"]["file"]["codec"] == "lines"


@pytest.mark.parametrize("path", ALL_PIPELINES, ids=lambda p: p.name)
def test_output_writes_stdout_lines(path):
    doc = _load(path)
    assert doc["config"]["output"]["stdout"]["codec"] == "lines"


@pytest.mark.parametrize("path", SDK_PIPELINES, ids=lambda p: p.name)
def test_sdk_pipeline_uses_subprocess_processor(path):
    doc = _load(path)
    procs = doc["config"]["pipeline"]["processors"]
    sub_procs = [p for p in procs if "subprocess" in p]
    assert len(sub_procs) == 1, f"{path.name} must have exactly one subprocess processor"
    sub = sub_procs[0]["subprocess"]
    assert sub["name"] == "uv"
    assert sub["args"][:2] == ["run", "-s"]
    provider = path.stem.replace("-sdk", "")
    expected_script = f"/scripts/{provider}_classify.py"
    assert sub["args"][2] == expected_script, (
        f"{path.name} should run {expected_script}, got {sub['args'][2]}"
    )


@pytest.mark.parametrize("path", HTTP_PIPELINES, ids=lambda p: p.name)
def test_http_pipeline_uses_branch_with_http(path):
    doc = _load(path)
    procs = doc["config"]["pipeline"]["processors"]
    branches = [p for p in procs if "branch" in p]
    assert len(branches) == 1, f"{path.name} must have exactly one branch processor"
    inner = branches[0]["branch"]["processors"]
    assert any("http" in p for p in inner), f"{path.name} branch must contain an http processor"


@pytest.mark.parametrize("path", HTTP_PIPELINES, ids=lambda p: p.name)
def test_http_pipeline_targets_correct_provider_host(path):
    doc = _load(path)
    branch = next(p for p in doc["config"]["pipeline"]["processors"] if "branch" in p)
    http = next(p for p in branch["branch"]["processors"] if "http" in p)
    url = http["http"]["url"]
    expected_host = EXPECTED_HOSTS[path.stem]
    assert expected_host in url, f"{path.name} should target {expected_host}, got {url}"


@pytest.mark.parametrize("path", HTTP_PIPELINES, ids=lambda p: p.name)
def test_http_pipeline_authenticates_via_env_var(path):
    doc = _load(path)
    branch = next(p for p in doc["config"]["pipeline"]["processors"] if "branch" in p)
    http = next(p for p in branch["branch"]["processors"] if "http" in p)
    headers = http["http"].get("headers", {})
    # All three providers should reference the API key via ${...} interpolation,
    # never as a hardcoded value.
    auth_header_values = list(headers.values())
    assert any("API_KEY" in str(v) for v in auth_header_values), (
        f"{path.name} must reference *_API_KEY env var in headers"
    )


@pytest.mark.parametrize("path", ALL_PIPELINES, ids=lambda p: p.name)
def test_pipeline_yaml_is_parseable(path):
    """Catches accidental YAML syntax errors before expanso-cli runs."""
    doc = yaml.safe_load(path.read_text())
    assert isinstance(doc, dict)
    assert "config" in doc
