from __future__ import annotations

import importlib.metadata
import json
import random
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from beatbloom.config import SAMPLE_RATE, ProjectConfig, SeparationConfig
from beatbloom.errors import BeatBloomError
from beatbloom.separation.cache import separate_audio
from beatbloom.separation.demucs import DemucsBackend


class SyntheticBackend:
    """Exercise real cache publication with deterministic stereo WAV outputs."""

    def __init__(self) -> None:
        self.calls = 0
        self.backend_version = "test-1"
        self.fail = False

    def versions(self) -> dict[str, str]:
        return {"test-backend": self.backend_version}

    def separate(self, audio: Path, destination: Path, config: SeparationConfig) -> dict[str, Path]:
        self.calls += 1
        if self.fail:
            raise BeatBloomError("separation failed")
        mono, rate = sf.read(audio, dtype="float32")
        stereo = np.column_stack([mono, mono]) if mono.ndim == 1 else mono
        paths = {}
        for index, stem in enumerate(config.stems):
            path = destination / f"{stem}.wav"
            sf.write(path, stereo * (index + 1) / len(config.stems), rate, subtype="FLOAT")
            paths[stem] = path
        return paths


@pytest.fixture
def synthetic_audio(tmp_path: Path) -> Path:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("FFmpeg required")
    path = tmp_path / "mix.wav"
    times = np.arange(SAMPLE_RATE // 4, dtype=np.float32) / SAMPLE_RATE
    sf.write(path, np.sin(2 * np.pi * 440 * times), SAMPLE_RATE, subtype="FLOAT")
    return path


@pytest.mark.integration
def test_separation_cache_reuses_all_stems_and_content_not_filename(
    synthetic_audio: Path, tmp_path: Path
) -> None:
    backend = SyntheticBackend()
    first = separate_audio(synthetic_audio, cache_dir=tmp_path / "cache", backend=backend)
    assert set(first.stems) == {"drums", "bass", "vocals", "other", "guitar", "piano"}
    assert not first.cached
    for path in first.stems.values():
        info = sf.info(path)
        assert (info.samplerate, info.channels, info.subtype) == (SAMPLE_RATE, 2, "FLOAT")
    renamed = tmp_path / "another name.wav"
    shutil.copyfile(synthetic_audio, renamed)
    second = separate_audio(renamed, cache_dir=tmp_path / "cache", backend=backend)
    assert second.cached and second.key == first.key
    assert backend.calls == 1


@pytest.mark.integration
@pytest.mark.parametrize("change", ["content", "model", "version", "seed", "corruption", "refresh"])
def test_separation_invalidation(synthetic_audio: Path, tmp_path: Path, change: str) -> None:
    backend = SyntheticBackend()
    config = SeparationConfig()
    first = separate_audio(synthetic_audio, config, cache_dir=tmp_path / "cache", backend=backend)
    if change == "content":
        sf.write(synthetic_audio, np.ones(1000, dtype=np.float32), SAMPLE_RATE, subtype="FLOAT")
    elif change == "model":
        config = SeparationConfig(model="htdemucs")
    elif change == "version":
        backend.backend_version = "test-2"
    elif change == "seed":
        config = SeparationConfig(seed=1)
    elif change == "corruption":
        first.stems["piano"].write_bytes(b"broken")
    second = separate_audio(
        synthetic_audio,
        config,
        cache_dir=tmp_path / "cache",
        backend=backend,
        refresh=change == "refresh",
    )
    assert not second.cached
    assert backend.calls == 2
    assert (second.key == first.key) == (change in {"corruption", "refresh"})


@pytest.mark.integration
def test_failed_refresh_preserves_stems(synthetic_audio: Path, tmp_path: Path) -> None:
    backend = SyntheticBackend()
    first = separate_audio(synthetic_audio, cache_dir=tmp_path / "cache", backend=backend)
    contents = {name: path.read_bytes() for name, path in first.stems.items()}
    backend.fail = True
    with pytest.raises(BeatBloomError, match="separation failed"):
        separate_audio(synthetic_audio, cache_dir=tmp_path / "cache", backend=backend, refresh=True)
    assert {name: path.read_bytes() for name, path in first.stems.items()} == contents
    assert separate_audio(synthetic_audio, cache_dir=tmp_path / "cache", backend=backend).cached
    assert not list((tmp_path / "cache/stems").glob(".*"))


def test_missing_extra_has_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_name: str) -> str:
        raise importlib.metadata.PackageNotFoundError("demucs")

    monkeypatch.setattr("beatbloom.separation.demucs.version", missing)
    with pytest.raises(BeatBloomError, match="uv sync --extra demucs"):
        DemucsBackend().versions()


@pytest.mark.integration
def test_requesting_another_stem_reuses_the_full_separation(
    synthetic_audio: Path, tmp_path: Path
) -> None:
    from beatbloom.analysis.pipeline import analyze

    backend = SyntheticBackend()
    for stem in ("piano", "drums", "guitar"):
        config = ProjectConfig.model_validate_json(
            json.dumps(
                {"schema_version": 2, "signals": {"energy": {"stem": stem, "feature": "rms"}}}
            )
        )
        result = analyze(synthetic_audio, config, cache_dir=tmp_path / "cache", backend=backend)
        assert result.stems_hit == (stem != "piano")
    assert backend.calls == 1


@pytest.mark.integration
@pytest.mark.demucs_runtime
def test_real_demucs_api_without_downloading_weights(
    synthetic_audio: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    torch = pytest.importorskip("torch")
    pytest.importorskip("demucs")
    from demucs import api
    from demucs.pretrained import get_model

    # The official tiny test model exercises real tensor separation, not a mock.
    monkeypatch.setattr(api, "get_model", lambda *_args, **_kwargs: get_model("demucs_unittest"))
    torch.set_num_threads(1)
    before = torch.random.get_rng_state().clone()
    random_before = random.getstate()
    stems = separate_audio(
        synthetic_audio,
        SeparationConfig(model="htdemucs", device="cpu", shifts=0, segment=1),
        cache_dir=tmp_path / "cache",
    )
    assert torch.equal(before, torch.random.get_rng_state())
    assert random.getstate() == random_before
    assert set(stems.stems) == {"drums", "bass", "vocals", "other"}
    expected_frames = sf.info(synthetic_audio).frames
    for path in stems.stems.values():
        samples, rate = sf.read(path, dtype="float32")
        assert samples.shape == (expected_frames, 2)
        assert rate == SAMPLE_RATE and np.all(np.isfinite(samples))

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("warm stems must not load or run a model")

    monkeypatch.setattr(api, "Separator", forbidden)
    assert separate_audio(
        synthetic_audio,
        SeparationConfig(model="htdemucs", device="cpu", shifts=0, segment=1),
        cache_dir=tmp_path / "cache",
    ).cached
