from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from beatbloom.config import (
    EffectConfig,
    ProjectConfig,
    SeparationConfig,
    SignalConfig,
    default_config,
    load_config,
)
from beatbloom.errors import BeatBloomError


def test_default_config_uses_named_signals_and_independent_mappings() -> None:
    config = default_config()
    assert config.schema_version == 2
    assert config.signals["volume_global"].feature == "loudness"
    assert config.effects[0].range == (0.6, 1.05)
    assert config.effects[1].amount == 1.2
    assert config.signals["piano_attaques"].reference == 99.5


def test_relative_source_paths(tmp_path: Path) -> None:
    directory = tmp_path / "configs"
    directory.mkdir()
    path = directory / "project.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "signals": {"kick": {"source": "../stems/drums.wav", "feature": "rms"}},
                "effects": [{"signal": "kick", "effect": "brightness", "range": [0.5, 1]}],
            }
        )
    )
    config = load_config(path)
    assert config.signals["kick"].source == str((tmp_path / "stems/drums.wav").resolve())
    assert config.effects[0].range == (0.5, 1.0)


@pytest.mark.parametrize("version", [None, 1, 2])
def test_legacy_bands_json_is_rejected(tmp_path: Path, version: int | None) -> None:
    payload: dict[str, object] = {"bands": [{"name": "kick", "effects": {"zoom": 0.006}}]}
    if version is not None:
        payload["schema_version"] = version
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(BeatBloomError, match="Legacy bands JSON is not supported"):
        load_config(path)


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
        ("source", ""),
        ("source", " "),
        ("stem", "strings"),
        ("name", "x"),
        ("effects", {"bloom": 1}),
        ("brightness", [0, 1]),
        ("gamma", "2.0"),
        ("gatee", 0.2),
    ],
)
def test_invalid_signal_fields_are_rejected(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        ProjectConfig.model_validate_json(
            json.dumps({"schema_version": 2, "signals": {"x": {field: value}}})
        )


def test_frequency_percentile_and_source_validation() -> None:
    with pytest.raises(ValidationError, match="low must be"):
        SignalConfig(low=1000.0, high=100.0)
    with pytest.raises(ValidationError, match="floor_percentile"):
        SignalConfig(feature="loudness", floor_percentile=99.0, ref_percentile=95.0)
    with pytest.raises(ValidationError, match="either source or stem"):
        SignalConfig(stem="drums", source="drums.wav")


@pytest.mark.parametrize(
    "payload",
    [
        {"signals": {"x": {}}},
        {"schema_version": 1, "signals": {"x": {}}},
        {"schema_version": 2, "signals": {}},
        {"schema_version": 2, "signals": {" ": {}}},
        {"schema_version": 2, "signals": {"x": {}}, "unknown": True},
        {
            "schema_version": 2,
            "signals": {"x": {}},
            "effects": [{"signal": "missing", "effect": "zoom", "amount": 1}],
        },
        {
            "schema_version": 2,
            "signals": {"x": {"stem": "piano"}},
            "separation": {"model": "htdemucs"},
        },
    ],
)
def test_invalid_project_config(payload: object) -> None:
    with pytest.raises(ValidationError):
        ProjectConfig.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "mapping",
    [
        {"signal": "x", "effect": "blom", "amount": 1},
        {"signal": "x", "effect": "bloom", "amount": -1},
        {"signal": "x", "effect": "bloom", "range": [0, 1]},
        {"signal": "x", "effect": "brightness", "amount": 1},
        {"signal": "x", "effect": "brightness", "range": [0, -1]},
        {"signal": "x", "effect": "brightness", "range": [0, 1], "amount": 1},
    ],
)
def test_invalid_effect_mapping(mapping: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        EffectConfig.model_validate_json(json.dumps(mapping))


@pytest.mark.parametrize(
    "options", [{"device": "oops"}, {"segment": 8}, {"overlap": 1}, {"shifts": -1}, {"seed": -1}]
)
def test_invalid_separation_options(options: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SeparationConfig.model_validate_json(json.dumps(options))


def test_read_and_parse_errors_are_user_facing(tmp_path: Path) -> None:
    with pytest.raises(BeatBloomError, match="Cannot read configuration"):
        load_config(tmp_path / "absent.json")
    path = tmp_path / "invalid.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(BeatBloomError, match="Invalid configuration"):
        load_config(path)


def test_all_repository_examples_validate() -> None:
    paths = sorted((Path(__file__).resolve().parents[1] / "examples").glob("*.json"))
    assert paths
    for path in paths:
        load_config(path)
