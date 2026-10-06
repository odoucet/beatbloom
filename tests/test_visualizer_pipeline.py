from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from beatbloom.analysis.pipeline import analyze
from beatbloom.config import ProjectConfig
from beatbloom.errors import BeatBloomError

pytestmark = pytest.mark.integration


def project(**changes: object) -> ProjectConfig:
    visualizer = {"type": "spectrum", "spectrum": {"n_fft": 512, "bands": 16}, **changes}
    return ProjectConfig.model_validate_json(
        json.dumps({"schema_version": 2, "visualizers": {"music": visualizer}})
    )


def test_warm_visualizers_and_style_changes_bypass_all_extraction(
    media_files: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, audio = media_files
    first = analyze(audio, project(), cache_dir=tmp_path / "cache")
    assert first.visualizer_hits == first.visualizer_feature_hits == 0

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("style-only changes must not decode audio or extract STFT")

    monkeypatch.setattr("beatbloom.analysis.pipeline.load_audio", forbidden)
    monkeypatch.setattr("beatbloom.analysis.visualizers.extract_spectrum", forbidden)
    changed = analyze(
        audio,
        project(
            height=0.3,
            opacity=0.2,
            layout="stacked",
            gain=2.0,
            tracks=[{"stem": "mix", "color": "#ff6633"}],
        ),
        cache_dir=tmp_path / "cache",
    )
    assert changed.visualizer_hits == 1
    assert first.manifest == changed.manifest
    np.testing.assert_array_equal(
        first.visualizers["music"][0].values, changed.visualizers["music"][0].values
    )


def test_smoothing_changes_reuse_raw_spectral_features(
    media_files: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, audio = media_files
    first = analyze(audio, project(), cache_dir=tmp_path / "cache")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("spectrum envelope changes must reuse raw log bands")

    monkeypatch.setattr("beatbloom.analysis.visualizers.extract_spectrum", forbidden)
    monkeypatch.setattr("beatbloom.analysis.pipeline.load_audio", forbidden)
    second = analyze(
        audio,
        project(
            spectrum={"n_fft": 512, "bands": 16, "release_ms": 700, "gamma": 2, "floor_db": -45}
        ),
        cache_dir=tmp_path / "cache",
    )
    assert second.visualizer_hits == 0 and second.visualizer_feature_hits == 1
    assert first.manifest != second.manifest


def test_waveform_window_and_resolution_are_display_only(
    media_files: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, audio = media_files
    first = analyze(audio, project(type="waveform"), cache_dir=tmp_path / "cache")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("waveform display changes must not extract peaks")

    monkeypatch.setattr("beatbloom.analysis.visualizers.extract_waveform", forbidden)
    second = analyze(
        audio,
        project(
            type="waveform", waveform={"window_seconds": 12, "points": 1000, "show_playhead": False}
        ),
        cache_dir=tmp_path / "cache",
    )
    assert second.visualizer_hits == 1 and first.manifest == second.manifest
    third = analyze(
        audio,
        project(type="waveform", waveform={"ref_percentile": 95}),
        cache_dir=tmp_path / "cache",
    )
    assert third.visualizer_hits == 0 and third.visualizer_feature_hits == 1


def test_frequency_band_changes_invalidate_spectral_extraction(
    media_files: tuple[Path, Path], tmp_path: Path
) -> None:
    _, audio = media_files
    first = analyze(audio, project(), cache_dir=tmp_path / "cache")
    second = analyze(
        audio,
        project(spectrum={"n_fft": 512, "bands": 32, "low": 100, "high": 8000}),
        cache_dir=tmp_path / "cache",
    )
    assert second.visualizer_hits == second.visualizer_feature_hits == 0
    assert first.manifest != second.manifest
    assert second.visualizers["music"][0].values.shape[1] == 32


def test_corrupt_visualizer_rebuilds_from_raw_features(
    media_files: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, audio = media_files
    first = analyze(audio, project(), cache_dir=tmp_path / "cache")
    manifest = json.loads(first.manifest.read_text())
    Path(manifest["visualizers"]["music"][0]["series"]).write_bytes(b"corrupt matrix")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("raw spectrum survives envelope corruption")

    monkeypatch.setattr("beatbloom.analysis.visualizers.extract_spectrum", forbidden)
    recovered = analyze(audio, project(), cache_dir=tmp_path / "cache")
    assert recovered.visualizer_hits == 0 and recovered.visualizer_feature_hits == 1
    np.testing.assert_array_equal(
        recovered.visualizers["music"][0].values, first.visualizers["music"][0].values
    )


def test_failed_visualizer_refresh_preserves_valid_cache(
    media_files: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, audio = media_files
    first = analyze(audio, project(), cache_dir=tmp_path / "cache")

    def failure(*_args: object, **_kwargs: object) -> None:
        raise BeatBloomError("failed extraction")

    monkeypatch.setattr("beatbloom.analysis.visualizers.extract_spectrum", failure)
    with pytest.raises(BeatBloomError, match="failed extraction"):
        analyze(audio, project(), cache_dir=tmp_path / "cache", refresh=True)
    recovered = analyze(audio, project(), cache_dir=tmp_path / "cache")
    assert recovered.visualizer_hits == 1
    np.testing.assert_array_equal(
        recovered.visualizers["music"][0].values, first.visualizers["music"][0].values
    )


def test_signals_waveform_and_spectrum_decode_each_source_once(
    media_files: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from beatbloom.analysis import pipeline

    _, audio = media_files
    original = pipeline.load_audio
    decoded: list[Path] = []

    def count(source: Path):
        decoded.append(source)
        return original(source)

    monkeypatch.setattr(pipeline, "load_audio", count)
    config = ProjectConfig.model_validate_json(
        json.dumps(
            {
                "schema_version": 2,
                "signals": {"energy": {"stem": "mix", "feature": "rms"}},
                "visualizers": {
                    "wave": {"type": "waveform"},
                    "frequency": {"type": "spectrum", "spectrum": {"n_fft": 512, "bands": 16}},
                },
            }
        )
    )
    result = analyze(audio, config, cache_dir=tmp_path / "cache")
    assert decoded == [audio.resolve()]
    assert result.signal_hits == result.visualizer_hits == 0


def test_duplicate_tracks_refresh_a_shared_feature_once(
    media_files: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from beatbloom.analysis import visualizers

    _, audio = media_files
    original = visualizers.extract_spectrum
    calls = 0

    def count(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(visualizers, "extract_spectrum", count)
    config = project(
        tracks=[{"stem": "mix", "color": "#ff0000"}, {"stem": "mix", "color": "#00ff00"}]
    )
    result = analyze(audio, config, cache_dir=tmp_path / "cache", refresh=True)
    assert calls == 1 and result.visualizer_hits == 1
