"""End-to-end proof: both published pipelines run in the runner image.

Each service starts the replay gateway and Expanso Edge in one container,
deploys the real pipeline, and must emit the committed expected records. The
container exits 0 by itself once four records appear, which also proves the
clean shutdown. Needs Docker; marked smoke so `pytest -m "not smoke"` skips it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
PROJECT = "agents-sdk-smoke"

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(shutil.which("docker") is None, reason="docker not installed"),
]


def _expected(name: str) -> dict[str, dict]:
    lines = (ROOT / "expected" / f"{name}.jsonl").read_text().splitlines()
    return {record["id"]: record for record in map(json.loads, lines)}


def _run(service: str) -> subprocess.CompletedProcess[str]:
    name = f"{PROJECT}-{service}"
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
    try:
        return subprocess.run(
            ["docker", "compose", "-p", PROJECT, "run", "--rm", "--name", name, service],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)


@pytest.fixture(scope="module", autouse=True)
def runner_image():
    subprocess.run(["docker", "compose", "-p", PROJECT, "build", "--quiet"], cwd=ROOT, check=True)


@pytest.mark.parametrize("service", ["gateway-http", "gateway-subprocess"])
def test_pipeline_emits_expected_records_and_exits_cleanly(service):
    result = _run(service)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    records = {}
    for line in result.stdout.splitlines():
        if line.startswith("{"):
            record = json.loads(line)
            records[record["id"]] = record
    assert records == _expected(service)
    # A clean stop: no warning or error lines from Edge or the subprocess.
    noisy = [ln for ln in result.stdout.splitlines() if " WRN " in ln or " ERR " in ln]
    assert noisy == []
    assert "already closed" not in result.stdout
