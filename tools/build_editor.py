"""Build a single offline HTML file from the current Python configuration models."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from beatbloom import __version__
from beatbloom.config import (
    NYQUIST,
    EffectConfig,
    ProjectConfig,
    SeparationConfig,
    SignalConfig,
    SpectrumConfig,
    VisualizerConfig,
    VisualizerTrackConfig,
    WaveformConfig,
    default_config,
)
from beatbloom.render.effects import BLOOM_SIGMA, BLOOM_THRESHOLD, LUMA

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "editor" / "beatbloom-editor.html"


def contract() -> dict[str, Any]:
    """Export schema, full factory defaults and shared effect constants, without media I/O."""
    project = default_config()
    names = {"volume_global": "global_volume", "piano_attaques": "piano_onsets"}
    project = project.model_copy(
        update={
            "signals": {names.get(name, name): signal for name, signal in project.signals.items()},
            "effects": tuple(
                effect.model_copy(update={"signal": names.get(effect.signal, effect.signal)})
                for effect in project.effects
            ),
        }
    )
    templates = {
        "SignalConfig": SignalConfig(stem="mix").model_dump(mode="json"),
        "SeparationConfig": SeparationConfig().model_dump(mode="json"),
        "VisualizerTrackConfig": VisualizerTrackConfig(stem="mix").model_dump(mode="json"),
        "WaveformConfig": WaveformConfig().model_dump(mode="json"),
        "SpectrumConfig": SpectrumConfig().model_dump(mode="json"),
        "VisualizerConfig": VisualizerConfig(type="waveform").model_dump(mode="json"),
    }
    effects = {item.effect: item.model_dump(mode="json") for item in project.effects}
    effects["zoom"] = EffectConfig(signal="piano_onsets", effect="zoom", amount=0.02).model_dump(
        mode="json"
    )
    starting = project.model_copy(
        update={
            "visualizers": {
                "waveform": VisualizerConfig(type="waveform", height=0.10, bottom=0.03),
                "spectrum": VisualizerConfig(
                    type="spectrum",
                    height=0.18,
                    bottom=0.16,
                    tracks=(VisualizerTrackConfig(stem="mix", color="#ffa76a"),),
                ),
            }
        }
    )
    schema = ProjectConfig.model_json_schema()
    fft = schema["$defs"]["SpectrumConfig"]["properties"]["n_fft"]
    fft_sizes = [
        2**power
        for power in range(int(fft["minimum"]).bit_length() - 1, int(fft["maximum"]).bit_length())
        if fft["minimum"] <= 2**power <= fft["maximum"]
    ]
    supported_effects = schema["$defs"]["EffectConfig"]["properties"]["effect"]["enum"]
    if set(effects) != set(supported_effects):
        raise ValueError("Add editor defaults and preview support for the new effect types")
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return {
        "beatbloomVersion": __version__,
        "editorVersion": "0.2-prep",
        "schemaHash": hashlib.sha256(canonical.encode()).hexdigest(),
        "schema": schema,
        "templates": templates,
        "effects": effects,
        "initialProject": starting.model_dump(mode="json"),
        "availableStems": {
            model: ["mix", *SeparationConfig(model=model).stems]
            for model in ("htdemucs", "htdemucs_6s")
        },
        "fftSizes": fft_sizes,
        "referencePercentiles": {
            feature: SignalConfig(feature=feature).reference
            for feature in schema["$defs"]["SignalConfig"]["properties"]["feature"]["enum"]
        },
        "nyquist": NYQUIST,
        "whitespace": "".join(chr(index) for index in range(0x110000) if chr(index).isspace()),
        "preview": {
            "width": 960,
            "height": 540,
            "timestamp": 8,
            "bloomThreshold": BLOOM_THRESHOLD,
            "bloomSigma": BLOOM_SIGMA,
            "luma": LUMA.tolist(),
        },
    }


def script_json(value: Any) -> str:
    """Prevent embedded JSON strings from closing a script element."""
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def build() -> str:
    source = ROOT / "editor" / "src"
    html = (source / "index.html").read_text(encoding="utf-8")
    replacements = {
        "@@STYLE@@": (source / "style.css").read_text(encoding="utf-8"),
        "@@CONTRACT@@": script_json(contract()),
        "@@CORE@@": (source / "core.js").read_text(encoding="utf-8"),
        "@@PREVIEW@@": (source / "preview.js").read_text(encoding="utf-8"),
        "@@MEDIA@@": (source / "media.js").read_text(encoding="utf-8"),
        "@@APP@@": (source / "app.js").read_text(encoding="utf-8"),
    }
    for marker, value in replacements.items():
        if html.count(marker) != 1:
            raise ValueError(f"Expected exactly one {marker} in the editor template")
        html = html.replace(marker, value)
    return html


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail when generated HTML is stale")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--contract", type=Path, help="Also write the development contract JSON")
    args = parser.parse_args()
    html = build()
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != html:
            parser.exit(1, "Editor is stale; run make editor and commit the generated HTML.\n")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(html, encoding="utf-8", newline="\n")
        print(args.output)
    if args.contract:
        args.contract.write_text(script_json(contract()) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
