"""Python-labeled cross-language validation fixtures for the offline editor."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from beatbloom.config import ProjectConfig

BASE: dict[str, Any] = {
    "schema_version": 2,
    "signals": {"energy": {}},
    "effects": [{"signal": "energy", "effect": "bloom", "amount": 0.1}],
    "visualizers": {"display": {"type": "spectrum", "tracks": [{"stem": "mix"}]}},
}


def cases() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    def add(name: str, data: dict[str, Any], expected: bool) -> None:
        try:
            ProjectConfig.model_validate_json(json.dumps(data))
            valid = True
        except ValidationError:
            valid = False
        if valid != expected:
            raise AssertionError(f"Fixture {name} has unexpected Python validity: {valid}")
        result.append({"name": name, "project": data, "valid": valid})

    add("factory-free defaults", copy.deepcopy(BASE), True)
    root = Path(__file__).resolve().parents[1]
    for file in sorted((root / "examples").glob("*.json")):
        add(file.name, json.loads(file.read_text()), True)
    valid = {
        "visualizer-only": {"schema_version": 2, "visualizers": {"v": {"type": "waveform"}}},
        "signal-only": {"schema_version": 2, "signals": {"s": {}}},
        "paths stay relative": {
            "schema_version": 2,
            "signals": {"s": {"source": "../音楽/piano.wav"}},
        },
        "prototype names": {
            "schema_version": 2,
            "signals": {"__proto__": {}, "constructor": {}},
            "effects": [{"signal": "__proto__", "effect": "zoom", "amount": 0.05}],
        },
        "minimal brightness": {
            "schema_version": 2,
            "signals": {"s": {}},
            "effects": [{"signal": "s", "effect": "brightness", "range": [0.0, 1.5]}],
        },
    }
    for name, data in valid.items():
        add(name, data, True)
    invalid: list[tuple[str, list[str | int], Any]] = [
        ("legacy schema", ["schema_version"], 1),
        ("unknown top-level", ["bands"], []),
        ("signal reference", ["effects", 0, "signal"], "missing"),
        ("missing additive amount", ["effects", 0, "amount"], None),
        ("brightness needs range", ["effects", 0, "effect"], "brightness"),
        ("additive range forbidden", ["effects", 0, "range"], [0.5, 1.5]),
        ("negative amount", ["effects", 0, "amount"], -0.1),
        ("blank source", ["signals", "energy", "source"], " \t\n"),
        ("Python-only blank source", ["signals", "energy", "source"], "\u001c"),
        ("wrong feature", ["signals", "energy", "feature"], "spectrogram"),
        ("equal frequencies", ["signals", "energy"], {"low": 100, "high": 100}),
        ("source and stem", ["signals", "energy"], {"source": "x.wav", "stem": "mix"}),
        ("negative attack", ["signals", "energy", "attack_ms"], -1),
        ("zero gamma", ["signals", "energy", "gamma"], 0),
        ("gate upper boundary", ["signals", "energy", "gate"], 1),
        ("zero percentile", ["signals", "energy", "ref_percentile"], 0),
        (
            "loudness percentiles",
            ["signals", "energy"],
            {"feature": "loudness", "floor_percentile": 99},
        ),
        ("missing stem", ["signals", "energy", "stem"], "flute"),
        ("signal number as string", ["signals", "energy", "gamma"], "1"),
        ("signal unknown field", ["signals", "energy", "mystery"], 1),
        ("tracks empty", ["visualizers", "display", "tracks"], []),
        ("tracks too many", ["visualizers", "display", "tracks"], [{}] * 17),
        ("track invalid color", ["visualizers", "display", "tracks", 0, "color"], "#fff"),
        ("color trailing newline", ["visualizers", "display", "tracks", 0, "color"], "#abcdef\n"),
        ("track source and stem", ["visualizers", "display", "tracks", 0, "source"], "x.wav"),
        ("region horizontal", ["visualizers", "display", "width"], 1),
        ("region vertical", ["visualizers", "display", "bottom"], 0.9),
        ("region zero width", ["visualizers", "display", "width"], 0),
        ("opacity upper bound", ["visualizers", "display", "opacity"], 1.1),
        ("invalid layout", ["visualizers", "display", "layout"], "rows"),
        ("FFT power", ["visualizers", "display", "spectrum", "n_fft"], 3000),
        ("FFT integer", ["visualizers", "display", "spectrum", "n_fft"], 4096.5),
        ("bands integer", ["visualizers", "display", "spectrum", "bands"], True),
        (
            "spectrum frequency order",
            ["visualizers", "display", "spectrum"],
            {"low": 400, "high": 100},
        ),
        ("spectrum floor boundary", ["visualizers", "display", "spectrum", "floor_db"], 0),
        ("waveform window", ["visualizers", "display", "waveform", "window_seconds"], 31),
        ("waveform boolean", ["visualizers", "display", "waveform", "show_playhead"], 1),
        ("device pattern", ["separation", "device"], "tpu"),
        ("device trailing newline", ["separation", "device"], "cpu\n"),
        ("overlap upper boundary", ["separation", "overlap"], 1),
        ("segment upper boundary", ["separation", "segment"], 8),
        ("seed upper boundary", ["separation", "seed"], 2**32),
    ]
    for name, path, value in invalid:
        data = copy.deepcopy(BASE)
        target = data
        for part in path[:-1]:
            target = target.setdefault(part, {}) if isinstance(target, dict) else target[part]
        target[path[-1]] = value
        add(name, data, False)
    add("empty project", {"schema_version": 2}, False)
    add("blank signal name", {"schema_version": 2, "signals": {" ": {}}}, False)
    add("Python-only blank name", {"schema_version": 2, "signals": {"\u001c": {}}}, False)
    add(
        "blank visualizer name",
        {"schema_version": 2, "visualizers": {"": {"type": "waveform"}}},
        False,
    )
    add(
        "piano with four stems",
        {
            "schema_version": 2,
            "separation": {"model": "htdemucs"},
            "signals": {"s": {"stem": "piano"}},
        },
        False,
    )
    return result


if __name__ == "__main__":
    print(json.dumps(cases(), ensure_ascii=False, allow_nan=False))
