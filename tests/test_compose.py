"""Structural tests for the one-shot Docker runners."""

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
    assert SERVICES[name]["command"] == [f"pipelines/{name}.yaml"]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_service_is_least_privilege(name):
    service = SERVICES[name]
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert "user" not in service or service["user"] not in {"0", "root"}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_service_needs_no_host_mounts(name):
    # A bare clone runs: the image carries the pipelines, data and fixtures.
    assert not SERVICES[name].get("volumes")


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_service_bounds_the_run_to_four_records(name):
    assert SERVICES[name]["environment"]["EXPECT_RECORDS"] == "4"


def test_no_service_sets_model_credentials():
    text = COMPOSE_PATH.read_text()
    assert "_API_" not in text
    assert "KEY" not in text
