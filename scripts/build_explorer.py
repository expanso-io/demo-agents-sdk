#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Embed the explorer contract into explorer/index.html.

    uv run -s scripts/build_explorer.py          rewrite the page
    uv run -s scripts/build_explorer.py --check  fail if the page is stale

`pipelines/explorer.json` is written by scripts/prove.py from real Edge runs.
This script copies that data into the page and writes one static, numbered
stage list per pipeline, so every stage exists in the published HTML before any
script runs.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "explorer" / "index.html"
CONTRACT = ROOT / "pipelines" / "explorer.json"


def stage_lists(contract: dict) -> str:
    blocks = []
    for number, path in enumerate(contract["paths"]):
        count = len(path["stages"])
        hidden = "" if number == 0 else " hidden"
        items = []
        for index, stage in enumerate(path["stages"], 1):
            current = ' aria-current="step"' if number == 0 and index == 1 else ""
            label = html.escape(f"Stage {index} of {count}: {stage['title']}", quote=True)
            items.append(
                f'    <li><button class="btn" type="button" '
                f'data-stage="{stage["data_stage"]}" aria-label="{label}"{current}>'
                f'<span class="n">{index}</span>'
                f'<span class="t">{html.escape(stage["title"])}</span></button></li>'
            )
        name = html.escape(path["title"], quote=True)
        blocks.append(
            f'  <ol class="stages" data-path-list="{path["id"]}" '
            f'aria-label="Stages: {name}"{hidden}>\n' + "\n".join(items) + "\n  </ol>"
        )
    return "\n".join(blocks)


def embedded(contract: dict) -> str:
    text = json.dumps(contract, indent=2, ensure_ascii=False).replace("</", "<\\/")
    return f'<script id="explorer-data" type="application/json">\n{text}\n</script>'


def replace(page: str, name: str, body: str) -> str:
    pattern = re.compile(rf"(<!-- {name}:start -->\n).*?(<!-- {name}:end -->)", re.S)
    if not pattern.search(page):
        raise SystemExit(f"explorer/index.html has no {name} markers")
    return pattern.sub(lambda m: m.group(1) + body + "\n" + m.group(2), page)


def render() -> str:
    contract = json.loads(CONTRACT.read_text())
    page = PAGE.read_text()
    page = replace(page, "stages", stage_lists(contract))
    return replace(page, "data", embedded(contract))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    fresh = render()
    if args.check:
        if PAGE.read_text() != fresh:
            print("FAIL: explorer/index.html is stale; run scripts/build_explorer.py")
            return 1
        print("explorer/index.html matches pipelines/explorer.json")
        return 0
    PAGE.write_text(fresh)
    print(f"wrote {PAGE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
