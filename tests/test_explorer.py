"""The explorer page, its contract and the manifest stay in step."""

from __future__ import annotations

import json
import re
import tomllib
from html.parser import HTMLParser
from pathlib import Path

import build_explorer
import pytest

ROOT = Path(__file__).parent.parent
PAGE = ROOT / "explorer" / "index.html"
CONTRACT = json.loads((ROOT / "pipelines" / "explorer.json").read_text())
MANIFEST = tomllib.loads((ROOT / "public-bar.toml").read_text())
FEATURES = json.loads((ROOT / "public-features.json").read_text())
TICKETS = [t["id"] for t in CONTRACT["tickets"]]
STAGES = [(p, s) for p in CONTRACT["paths"] for s in p["stages"]]


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.stages: list[str] = []
        self.pre_blocks: list[str] = []
        self._pre = False
        self._buffer: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if "data-stage" in attrs:
            self.stages.append(attrs["data-stage"])
        if tag == "pre":
            self._pre, self._buffer = True, []

    def handle_endtag(self, tag):
        if tag == "pre" and self._pre:
            self.pre_blocks.append("".join(self._buffer))
            self._pre = False

    def handle_data(self, data):
        if self._pre:
            self._buffer.append(data)


def _page() -> Page:
    parser = Page()
    parser.feed(PAGE.read_text())
    return parser


def _without_data(text: str) -> str:
    return re.sub(r"<!-- data:start -->.*?<!-- data:end -->", "", text, flags=re.S)


def test_page_matches_contract():
    assert PAGE.read_text() == build_explorer.render()


def test_every_stage_is_published_statically():
    assert sorted(_page().stages) == sorted(s["data_stage"] for _, s in STAGES)


def test_page_has_the_four_published_sections():
    assert {"explanation", "explorer", "run", "deploy"} <= _page().ids


@pytest.mark.parametrize("path,stage", STAGES, ids=lambda v: v if isinstance(v, str) else None)
def test_stage_fixtures_equal_what_the_page_shows(path, stage):
    for side in ("input", "output"):
        lines = (ROOT / stage["fixtures"][side]).read_text().splitlines()
        assert [json.loads(line) for line in lines] == [stage["io"][t][side] for t in TICKETS]


def test_every_pipeline_stage_in_the_manifest_matches_the_contract():
    declared = {s["id"]: s for s in MANIFEST["stages"]}
    expected = {f"{p['id']}-{s['id']}": (p, s) for p, s in STAGES}
    assert set(declared) == set(expected)
    for ident, (path, stage) in expected.items():
        assert declared[ident]["pipeline"] == path["id"]
        assert declared[ident]["selector"] == f"[data-stage='{stage['data_stage']}']"
        assert declared[ident]["input"] == stage["fixtures"]["input"]
        assert declared[ident]["output"] == stage["fixtures"]["output"]
    assert {f["id"] for f in FEATURES["features"]} >= set(declared)


def test_every_manifest_control_exists_on_the_page():
    ids = _page().ids
    for control in MANIFEST["browser"]["controls"]:
        for key in ("selector", "feedback_selector"):
            assert control[key].startswith("#")
            assert control[key][1:] in ids, control["id"]


def test_pipelines_in_the_manifest_have_goldens():
    for pipeline in MANIFEST["pipelines"]:
        assert (ROOT / pipeline["path"]).is_file()
        assert (ROOT / pipeline["expected"]).is_file()


def test_goldens_agree_with_the_recorded_answers():
    recorded = {}
    for path in (ROOT / "fixtures" / "model").glob("*.json"):
        record = json.loads(path.read_text())
        recorded[record["name"].removeprefix("support-")] = json.loads(record["text"])
    for pipeline in MANIFEST["pipelines"]:
        for line in (ROOT / pipeline["expected"]).read_text().splitlines():
            record = json.loads(line)
            answer = recorded[record["id"]]
            assert {k: record[k] for k in answer} == answer


def test_the_walk_covers_the_shipped_tickets_and_the_failure_case():
    shipped = [
        json.loads(x)["id"] for x in (ROOT / "data" / "events.jsonl").read_text().splitlines()
    ]
    assert TICKETS[: len(shipped)] == shipped
    assert [t["kind"] for t in CONTRACT["tickets"]][-1] == "no recorded answer"


def test_gateway_vendor_metadata_is_not_shown():
    text = PAGE.read_text()
    for field in CONTRACT["omitted_gateway_fields"]:
        assert f'"{field}":' not in text
    assert "gemini" not in text.lower()


# ---------------------------------------------------------------- presentation


def _tokens(selector: str) -> dict[str, str]:
    css = (ROOT / "explorer" / "explorer.css").read_text()
    block = re.search(re.escape(selector) + r"\s*\{(.*?)\}", css, re.S).group(1)
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", block))


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _ratio(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("selector", [":root", ':root[data-theme="dark"]'])
def test_text_tokens_meet_wcag_aa_on_every_ground(selector):
    tokens = _tokens(":root") | (_tokens(selector) if selector != ":root" else {})
    grounds = [tokens[n] for n in ("bg", "surface", "surface-2")]
    for name in ("text", "text-dim", "accent", "ok", "err", "warn"):
        for ground in grounds:
            assert _ratio(tokens[name], ground) >= 4.5, (selector, name, ground)
    assert _ratio(tokens["on-accent"], tokens["accent"]) >= 4.5
    for ground in grounds[:2]:
        assert _ratio(tokens["line-strong"], ground) >= 3, (selector, "control border")


def test_light_is_the_default_theme():
    assert 'data-theme="light"' in PAGE.read_text().split(">", 3)[1] + ">"
    script = (ROOT / "explorer" / "explorer.js").read_text()
    assert 'saved === "dark" ? "dark" : "light"' in script
    assert "prefers-color-scheme" not in (ROOT / "explorer" / "explorer.css").read_text()


def test_fonts_are_vendored_not_system_or_cdn():
    css = (ROOT / "explorer" / "explorer.css").read_text()
    faces = re.findall(r'url\("(fonts/[^"]+)"\)', css)
    assert faces and all((ROOT / "explorer" / face).is_file() for face in faces)
    banned = re.compile(r"\b(Inter|Roboto|Arial|Helvetica|system-ui|Geist)\b", re.I)
    assert not banned.search(css)


def test_nothing_loads_from_the_network():
    for name in ("index.html", "explorer.css", "explorer.js"):
        text = _without_data((ROOT / "explorer" / name).read_text())
        assert not re.search(r"https?://(?!127\.0\.0\.1)", text), name


def test_no_decorative_side_stripes_grids_or_eyebrow_labels():
    css = (ROOT / "explorer" / "explorer.css").read_text()
    assert not re.search(r"border-(left|right)\s*:\s*[2-9]px", css)
    assert "linear-gradient" not in css and "radial-gradient" not in css
    assert "text-transform: uppercase" not in css
    assert "box-shadow" not in css


def test_code_blocks_wrap_so_nothing_scrolls_sideways():
    css = (ROOT / "explorer" / "explorer.css").read_text()
    assert "white-space: pre-wrap" in css
    assert "overflow-x" not in css


def test_published_commands_fit_in_seventy_columns():
    for block in _page().pre_blocks:
        for line in block.splitlines():
            assert len(line) <= 70, line


def test_commands_on_the_page_are_the_ones_the_repo_ships():
    commands = "\n".join(_page().pre_blocks)
    assert "docker compose run --rm gateway-http" in commands
    assert "docker compose run --rm gateway-subprocess" in commands
    assert "deploy/docker-compose.node.yaml" in commands


BANNED_WORDING = re.compile(r"illustrative|modeled|simulated|demo scale|\bsimulat", re.I)


def test_no_hedging_labels_on_measured_results():
    texts = [
        _without_data(PAGE.read_text()),
        (ROOT / "README.md").read_text(),
        *(p.read_text() for p in (ROOT / "reports").glob("*.md")),
    ]
    for text in texts:
        assert not BANNED_WORDING.search(text)


def test_page_copy_has_no_em_dashes():
    for name in ("index.html", "explorer.css", "explorer.js"):
        assert "—" not in _without_data((ROOT / "explorer" / name).read_text())
    assert "—" not in (ROOT / "README.md").read_text()
