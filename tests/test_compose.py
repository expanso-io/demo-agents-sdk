"""Structural tests for docker-compose.yaml.

Asserts the wiring contracts: 6 services exist, each runs the correct pipeline
file via the runner image, and each mounts pipelines/scripts/data with the
right env vars. These catch regressions that would otherwise only surface at
`docker compose run` time.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

COMPOSE_PATH = Path(__file__).parent.parent / "docker-compose.yaml"
COMPOSE = yaml.safe_load(COMPOSE_PATH.read_text())
SERVICES = COMPOSE["services"]

EXPECTED = {
    "openai-http",
    "openai-sdk",
    "anthropic-http",
    "anthropic-sdk",
    "gemini-http",
    "gemini-sdk",
}


def test_all_six_services_present():
    assert set(SERVICES.keys()) == EXPECTED


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_service_runs_matching_pipeline_file(name):
    # The runner image's entrypoint (`run-demo`) takes only the pipeline path —
    # it handles `expanso-edge run --local` + `expanso-cli job deploy`
    # internally so a single `docker compose run` lifts the whole stack.
    assert SERVICES[name]["command"] == [f"/pipelines/{name}.yaml"]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_service_builds_local_runner(name):
    svc = SERVICES[name]
    assert svc["build"] == "."
    assert svc["image"] == "demo-agents-sdk-runner"


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_service_mounts_pipelines_and_data(name):
    mounts = SERVICES[name]["volumes"]
    assert any("./pipelines:/pipelines" in m for m in mounts)
    assert any("./data:/data" in m for m in mounts)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_service_mounts_scripts_and_uv_cache(name):
    # Every service mounts scripts/ + uv-cache because the runner image is
    # shared — even HTTP-direct pipelines run through it.
    mounts = SERVICES[name]["volumes"]
    assert any("./scripts:/scripts" in m for m in mounts), f"{name} must mount ./scripts"
    assert any("uv-cache:/root/.cache/uv" in m for m in mounts), (
        f"{name} must share the uv-cache named volume"
    )


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_service_exposes_provider_env_vars(name):
    provider = name.split("-", 1)[0].upper()
    env = SERVICES[name]["environment"]
    assert f"{provider}_API_KEY" in env
    assert f"{provider}_MODEL" in env


def test_uv_cache_volume_declared_at_top_level():
    assert "uv-cache" in COMPOSE.get("volumes", {})


def test_no_service_hardcodes_secrets():
    """Defense in depth: catch accidental literal API keys in compose env."""
    for name, svc in SERVICES.items():
        for entry in svc.get("environment", []):
            # Compose env entries should be `KEY` (passthrough) or `KEY=value`
            # where value is empty/literal-test. Reject anything that looks
            # like a real key.
            if "=" in entry:
                value = entry.split("=", 1)[1]
                assert "sk-" not in value, f"{name} appears to embed a real key: {entry}"
                assert "AIza" not in value, f"{name} appears to embed a Google key: {entry}"
