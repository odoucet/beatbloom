from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from beatbloom.config import BandConfig, ProjectConfig, default_config, load_config
from beatbloom.errors import BeatBloomError


def test_default_config_matches_prototype() -> None:
    config = default_config()
    assert config.bands[0].brightness == (0.6, 1.05)
    assert config.bands[0].feature == "loudness"
    assert config.bands[1].effects["bloom"] == 1.2
    assert config.bands[1].reference == 99.5


def test_legacy_json_and_relative_source_paths(tmp_path: Path) -> None:
    directory = tmp_path / "configs"
    directory.mkdir()
    path = directory / "bands.json"
    path.write_text(
        json.dumps(
            {
                "bands": [
                    {
                        "name": "kick",
                        "source": "../stems/drums.wav",
                        "low": 40,
                        "high": 120,
                        "feature": "rms",
                        "brightness": [0.5, 1],
                        "effects": {"zoom": 0.01},
                    }
                ]
            }
        )
    )
    band = load_config(path).bands[0]
    assert band.source == str((tmp_path / "stems/drums.wav").resolve())
    assert band.brightness == (0.5, 1.0)


@pytest.mark.parametrize(
    "field,value",
    [
        ("gate", 1),
        ("gate", -0.01),
        ("gamma", 0),
        ("gamma", float("nan")),
        ("attack_ms", -1),
        ("release_ms", float("inf")),
        ("low", -1),
        ("high", 30_000),
        ("ref_percentile", 101),
        ("feature", "beats"),
        ("name", " "),
        ("source", ""),
        ("effects", {"blom": 1}),
        ("effects", {"bloom": -1}),
        ("brightness", [1]),
        ("brightness", [0, -1]),
        ("gamma", "2.0"),
        ("gatee", 0.2),
    ],
)
def test_invalid_band_fields_are_rejected(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        ProjectConfig.model_validate_json(json.dumps({"bands": [{"name": "x", field: value}]}))


def test_invalid_frequency_and_percentile_order() -> None:
    with pytest.raises(ValidationError, match="low must be"):
        BandConfig(name="bad", low=1000.0, high=100.0)
    with pytest.raises(ValidationError, match="floor_percentile"):
        BandConfig(name="bad", feature="loudness", floor_percentile=99.0, ref_percentile=95.0)


@pytest.mark.parametrize(
    "payload",
    [
        {"bands": []},
        {"bands": [{"name": "x"}, {"name": "x"}]},
        {"schema_version": 2, "bands": [{"name": "x"}]},
        {"bands": [{"name": "x"}], "unknown": True},
    ],
)
def test_invalid_project_config(payload: object) -> None:
    with pytest.raises(ValidationError):
        ProjectConfig.model_validate_json(json.dumps(payload))


def test_read_and_parse_errors_are_user_facing(tmp_path: Path) -> None:
    with pytest.raises(BeatBloomError, match="Cannot read configuration"):
        load_config(tmp_path / "absent.json")
    path = tmp_path / "invalid.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(BeatBloomError, match="Invalid configuration"):
        load_config(path)


def test_all_repository_examples_validate() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = sorted((root / "examples").glob("*.json"))
    assert paths
    for path in paths:
        load_config(path)
