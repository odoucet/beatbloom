"""Synthetic media fixtures; no bundled songs, videos or model downloads."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from beatbloom.config import SAMPLE_RATE
from beatbloom.models import AudioTrack


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "beatbloom.cache.user_cache_path", lambda *_args, **_kwargs: tmp_path / "cache"
    )


@pytest.fixture
def track() -> AudioTrack:
    times = np.arange(SAMPLE_RATE * 2, dtype=np.float32) / SAMPLE_RATE
    amplitude = np.where(times < 1, 0.15, 0.8)
    samples = amplitude * np.sin(2 * np.pi * 800 * times)
    return AudioTrack(samples.astype(np.float32), SAMPLE_RATE)


@pytest.fixture(scope="session")
def media_files(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("FFmpeg and ffprobe are required for integration tests")
    root = tmp_path_factory.mktemp("synthetic media with spaces")
    video, audio = root / "video input.mp4", root / "audio mix.wav"
    for command in (
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x607080:s=64x48:r=12:d=2",
            "-an",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=800:sample_rate=44100:duration=2",
            "-c:a",
            "pcm_s16le",
            str(audio),
        ],
    ):
        subprocess.run(command, check=True, capture_output=True)
    return video, audio
