"""Structural tests for the fixture-mode Docker runners."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

COMPOSE_PATH = Path(__file__).parent.parent / "docker-compose.yaml"
SERVICES = yaml.safe_load(COMPOSE_PATH.read_text())["services"]
EXPECTED = {"gateway-http", "gateway-subprocess"}


def test_both_gateway_integration_paths_exist():
    assert set(SERVICES) == EXPECTED


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_service_runs_matching_pipeline(name):
    assert SERVICES[name]["command"] == [f"/pipelines/{name}.yaml"]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_service_mounts_demo_kit_and_fixture_store(name):
    mounts = SERVICES[name]["volumes"]
    assert "../_demo-kit:/demo-kit:ro" in mounts
    assert "./:/workspace:ro" in mounts
    assert "./data:/data:ro" in mounts


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_service_sets_only_gateway_config(name):
    assert SERVICES[name]["environment"] == ["MODEL_GATEWAY_CONFIG=/workspace/model-gateway.toml"]


def test_no_service_sets_model_credentials():
    text = COMPOSE_PATH.read_text()
    assert "_API_" not in text
