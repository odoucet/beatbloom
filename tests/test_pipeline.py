from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from beatbloom.analysis.pipeline import analyze
from beatbloom.config import SAMPLE_RATE, EffectConfig, ProjectConfig, SignalConfig

pytestmark = pytest.mark.integration


def project(signal: SignalConfig | None = None, *, amount: float = 1.0) -> ProjectConfig:
    return ProjectConfig(
        schema_version=2,
        signals={"energy": signal or SignalConfig(feature="rms", attack_ms=0.0, release_ms=0.0)},
        effects=(EffectConfig(signal="energy", effect="bloom", amount=amount),),
    )


def test_effect_changes_and_renaming_reuse_signals_without_decoding(
    media_files: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, audio = media_files
    first = analyze(audio, project(), cache_dir=tmp_path / "cache")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("warm signal cache must bypass audio decoding and extraction")

    monkeypatch.setattr("beatbloom.analysis.pipeline.load_audio", forbidden)
    monkeypatch.setattr("beatbloom.analysis.pipeline.extract_features", forbidden)
    renamed = tmp_path / "renamed.wav"
    shutil.copyfile(audio, renamed)
    changed = analyze(renamed, project(amount=8.0), cache_dir=tmp_path / "cache")
    assert changed.signal_hits == 1 and changed.feature_hits == 0
    assert first.manifest == changed.manifest
    np.testing.assert_array_equal(first.signals["energy"].values, changed.signals["energy"].values)


def test_envelope_tuning_reuses_raw_features(
    media_files: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, audio = media_files
    analyze(audio, project(), cache_dir=tmp_path / "cache")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("envelope changes must not re-extract raw audio features")

    monkeypatch.setattr("beatbloom.analysis.pipeline.extract_features", forbidden)
    monkeypatch.setattr("beatbloom.analysis.pipeline.load_audio", forbidden)
    for feature in ("rms", "loudness"):
        config = project(SignalConfig(feature=feature, gamma=2.0, release_ms=123.0))
        result = analyze(audio, config, cache_dir=tmp_path / "cache")
        assert result.feature_hits == 1 and result.signal_hits == 0


def test_changed_content_invalidates_even_with_same_size_and_mtime(
    media_files: tuple[Path, Path], tmp_path: Path
) -> None:
    _, original = media_files
    audio = tmp_path / "changing.wav"
    shutil.copyfile(original, audio)
    first = analyze(audio, project(), cache_dir=tmp_path / "cache")
    stat = audio.stat()
    samples, _rate = sf.read(audio, dtype="int16")
    with audio.open("r+b") as stream:
        stream.seek(-samples.nbytes, 2)
        stream.write((samples // 2).astype("<i2").tobytes())
    os.utime(audio, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert audio.stat().st_size == stat.st_size
    second = analyze(audio, project(), cache_dir=tmp_path / "cache")
    assert second.manifest != first.manifest
    assert second.signal_hits == second.feature_hits == 0


def test_native_timestamps_and_full_track_normalization(track, tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("FFmpeg required")
    audio = tmp_path / "two energy levels.wav"
    sf.write(audio, track.samples, SAMPLE_RATE, subtype="FLOAT")
    result = analyze(audio, project(), cache_dir=tmp_path / "cache")
    signal = result.signals["energy"]
    np.testing.assert_allclose(np.diff(signal.timestamps), 256 / SAMPLE_RATE)
    assert 0 < signal.at(0.5) < signal.at(1.5) * 0.3
    assert signal.at(2.0) == 0
    manifest = json.loads(result.manifest.read_text())
    assert manifest["audio_duration"] == 2.0
    assert "effects" not in manifest["parameters"]


def test_explicit_mix_ignores_drive_and_default_signal_uses_it(
    media_files: tuple[Path, Path], tmp_path: Path
) -> None:
    _, audio = media_files
    silent = tmp_path / "silent.wav"
    sf.write(silent, np.zeros(SAMPLE_RATE * 2, dtype=np.float32), SAMPLE_RATE, subtype="FLOAT")
    config = ProjectConfig(
        schema_version=2,
        signals={
            "mix": SignalConfig(stem="mix", feature="rms"),
            "drive": SignalConfig(feature="rms"),
        },
    )
    result = analyze(audio, config, drive=silent, cache_dir=tmp_path / "cache")
    assert np.max(result.signals["mix"].values) > 0.5
    assert np.all(result.signals["drive"].values == 0)
