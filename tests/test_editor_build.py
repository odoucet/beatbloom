"""Check the Python/browser contract and deterministic offline artifact."""

from __future__ import annotations

import json
import re
import runpy
import subprocess
import sys
from pathlib import Path

from beatbloom.config import (
    ProjectConfig,
    SeparationConfig,
    SignalConfig,
    SpectrumConfig,
    VisualizerConfig,
    VisualizerTrackConfig,
    WaveformConfig,
)

ROOT = Path(__file__).resolve().parents[1]
BUILDER = runpy.run_path(str(ROOT / "tools" / "build_editor.py"))


def test_generated_editor_is_current() -> None:
    html = (ROOT / "editor" / "beatbloom-editor.html").read_text(encoding="utf-8")
    assert BUILDER["build"]() == html


def test_contract_uses_actual_model_defaults() -> None:
    contract = BUILDER["contract"]()
    assert contract["schema"] == ProjectConfig.model_json_schema()
    for model in (SignalConfig, SeparationConfig, SpectrumConfig, WaveformConfig):
        expected = model(stem="mix") if model is SignalConfig else model()
        assert contract["templates"][model.__name__] == expected.model_dump(mode="json")
    assert contract["templates"]["VisualizerConfig"] == VisualizerConfig(
        type="waveform"
    ).model_dump(mode="json")
    assert contract["templates"]["VisualizerTrackConfig"] == VisualizerTrackConfig(
        stem="mix"
    ).model_dump(mode="json")
    ProjectConfig.model_validate_json(json.dumps(contract["initialProject"]))


def test_embedded_json_cannot_close_its_script() -> None:
    value = {"name": "</script><script>alert('x')</script>\u2028\u2029"}
    encoded = BUILDER["script_json"](value)
    assert "<" not in encoded
    assert json.loads(encoded) == value


def test_check_reports_a_stale_artifact(tmp_path: Path) -> None:
    output = tmp_path / "editor.html"
    output.write_text("stale", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "build_editor.py"),
            "--check",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "Editor is stale" in result.stderr
    assert output.read_text() == "stale"


def test_html_embeds_parseable_contract() -> None:
    html = BUILDER["build"]()
    match = re.search(
        r'<script id="beatbloom-contract" type="application/json">(.*?)</script>', html, re.S
    )
    assert match is not None
    contract = json.loads(match[1])
    assert contract == BUILDER["contract"]()
