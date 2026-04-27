"""End-to-end smoke test using a stub classifier — proves the whole stack
(runner image, expanso-edge subprocess processor, pipeline IO) wires up
correctly without needing a real API key.

Slow (~30s on warm cache, ~2 min cold). Marked with @pytest.mark.smoke so
local dev can skip it via `pytest -m 'not smoke'`. CI runs unconditionally.

Strategy: launch the runner image with the smoke pipeline and the fixture
echo_classify.py mounted at /scripts. The pipeline emits one JSONL line per
input event to stdout; we parse those and assert structure.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"


def _docker_available() -> bool:
    return shutil.which("docker") is not None


pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(not _docker_available(), reason="docker not installed"),
]


@pytest.fixture(scope="module")
def runner_image() -> str:
    """Build the runner image once for the whole module."""
    image_tag = "demo-agents-sdk-runner:smoke"
    subprocess.run(
        ["docker", "build", "--quiet", "-t", image_tag, "."],
        cwd=ROOT,
        check=True,
    )
    return image_tag


def test_runner_image_has_uv_and_python(runner_image):
    """Sanity check: the layered image has uv on PATH and a usable Python."""
    out = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "uv", runner_image, "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "uv" in out.stdout.lower()


def test_smoke_pipeline_classifies_all_events(runner_image):
    """Run the smoke pipeline through the real expanso-edge binary against
    the stub classifier. Assert each input event produces a classified
    output line with the expected schema.

    Edge keeps its management API up after the pipeline drains, so we run
    the container detached, poll `docker logs` for our 8 classified lines,
    then force-remove the container. This avoids blocking on `readline()`
    against a daemon that doesn't close stdout."""
    container_name = "demo-agents-sdk-smoke-test"
    # Make sure no leftover container from a previous run is around.
    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, check=False)

    cid = subprocess.run(
        [
            "docker",
            "run",
            "--detach",
            "--name",
            container_name,
            "-v",
            f"{FIXTURES}:/pipelines:ro",
            "-v",
            f"{ROOT / 'data'}:/data:ro",
            "-v",
            f"{FIXTURES}:/scripts:ro",
            runner_image,
            "/pipelines/smoke-pipeline.yaml",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert cid, "docker run --detach should have printed a container id"

    classified: list[dict] = []
    last_logs = ""
    deadline = time.time() + 90  # cold uv resolve + 8 events + slack
    try:
        while time.time() < deadline:
            time.sleep(2)
            logs = subprocess.run(
                ["docker", "logs", container_name],
                capture_output=True,
                text=True,
                check=False,
            ).stdout
            last_logs = logs
            classified = []
            for line in logs.splitlines():
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("_provider") == "stub":
                    classified.append(obj)
            if len(classified) >= 8:
                break
    finally:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, check=False)

    assert len(classified) == 8, (
        f"expected 8 classifications, got {len(classified)}\n"
        f"--- last container logs ---\n{last_logs[-3000:]}"
    )

    # Each must carry the shared schema.
    for obj in classified:
        assert obj["_provider"] == "stub"
        assert obj["_mode"] == "subprocess"
        assert obj["category"] in {"billing", "technical", "account", "other"}
        assert obj["sentiment"] in {"pos", "neg", "neu"}
        assert obj["priority"] in {"low", "med", "high"}

    # Verify deterministic behavior: T-001 (billing message) must classify as billing.
    by_id = {obj["id"]: obj for obj in classified}
    assert by_id["T-001"]["category"] == "billing"
    assert by_id["T-005"]["category"] == "technical"  # "URGENT: production is down"
    assert by_id["T-005"]["priority"] == "high"
