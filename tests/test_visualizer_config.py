from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from beatbloom.config import ProjectConfig, SpectrumConfig, VisualizerConfig, load_config


def test_v02_projects_remain_valid_without_visualizers() -> None:
    config = ProjectConfig.model_validate_json(
        '{"schema_version":2,"signals":{"energy":{"feature":"rms"}}}'
    )
    assert config.visualizers == {}


def test_visualizer_only_project_and_relative_source(tmp_path: Path) -> None:
    path = tmp_path / "visuals.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "visualizers": {
                    "wave": {
                        "type": "waveform",
                        "tracks": [{"source": "stems/other.wav", "color": "#ff6633"}],
                    }
                },
            }
        )
    )
    config = load_config(path)
    assert not config.signals and not config.effects
    assert config.visualizers["wave"].tracks[0].source == str(tmp_path / "stems/other.wav")


@pytest.mark.parametrize(
    "settings",
    [
        {"type": "unknown"},
        {"height": 0},
        {"height": 0.99},
        {"width": 1},
        {"opacity": -0.1},
        {"opacity": 1.1},
        {"bottom": -1},
        {"gap": 0.5},
        {"tracks": []},
        {"tracks": [{"color": "red"}]},
        {"tracks": [{"color": "#1234567"}]},
        {"tracks": [{"source": "x.wav", "stem": "drums"}]},
        {"tracks": [{"source": " "}]},
        {"layout": "grid"},
        {"line_width": 0},
        {"bar_gap": 1},
        {"gain": -1},
        {"spectrum": {"n_fft": 1000}},
        {"spectrum": {"low": 1000, "high": 100}},
        {"spectrum": {"floor_db": 0}},
        {"spectrum": {"bands": 2}},
        {"waveform": {"window_seconds": 0}},
        {"waveform": {"points": 1}},
    ],
)
def test_invalid_visualizer_settings(settings: dict[str, object]) -> None:
    payload = {"type": "spectrum", **settings}
    with pytest.raises(ValidationError):
        VisualizerConfig.model_validate_json(json.dumps(payload))


def test_invalid_stem_and_visualizer_name_are_rejected() -> None:
    for visualizers in (
        {" ": {"type": "spectrum"}},
        {"keys": {"type": "spectrum", "tracks": [{"stem": "piano"}]}},
    ):
        with pytest.raises(ValidationError):
            ProjectConfig.model_validate_json(
                json.dumps(
                    {
                        "schema_version": 2,
                        "separation": {"model": "htdemucs"},
                        "visualizers": visualizers,
                    }
                )
            )


def test_log_spectrum_range_is_bounded_by_analysis_nyquist() -> None:
    with pytest.raises(ValidationError):
        SpectrumConfig(high=24000.0)
