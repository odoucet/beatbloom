"""Turn complete audio tracks into named, normalized signals."""

from __future__ import annotations

import logging
import math
import warnings
from pathlib import Path

import librosa
import numpy as np

from beatbloom.analysis.envelopes import normalize, smooth
from beatbloom.analysis.filters import filter_band
from beatbloom.config import SAMPLE_RATE, BandConfig, ProjectConfig
from beatbloom.errors import BeatBloomError
from beatbloom.media import load_audio
from beatbloom.models import AudioTrack, FloatArray, Signal

HOP_LENGTH = 256
FRAME_LENGTH = 2048
LOGGER = logging.getLogger(__name__)


def band_envelope(track: AudioTrack, band: BandConfig, fps: float) -> Signal:
    """Analyze and normalize the entire source before any render excerpt is selected."""
    if track.sample_rate != SAMPLE_RATE:
        raise BeatBloomError(f"Expected {SAMPLE_RATE} Hz PCM, got {track.sample_rate} Hz")
    samples = filter_band(track.samples, band)
    if band.feature == "onset":
        # Librosa's centered STFT supports short clips, but emits this advisory warning.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="n_fft=.*is too large", category=UserWarning)
            features = librosa.onset.onset_strength(
                y=samples, sr=SAMPLE_RATE, hop_length=HOP_LENGTH
            )
    else:
        features = librosa.feature.rms(y=samples, frame_length=FRAME_LENGTH, hop_length=HOP_LENGTH)[
            0
        ]
    count = math.ceil(track.duration * fps) + 1
    feature_times = np.arange(len(features), dtype=np.float64) * HOP_LENGTH / SAMPLE_RATE
    values = np.asarray(
        np.interp(np.arange(count, dtype=np.float64) / fps, feature_times, features),
        dtype=np.float32,
    )
    envelope: FloatArray = smooth(normalize(values, band), band, fps)
    return Signal(band.name, envelope, fps, track.duration)


def analyze_bands(
    config: ProjectConfig,
    default_source: Path,
    fps: float,
    tracks: dict[Path, AudioTrack] | None = None,
) -> tuple[Signal, ...]:
    """Reuse decoded sources within a run; persistent analysis caching comes in v0.2."""
    decoded = tracks if tracks is not None else {}
    signals: list[Signal] = []
    for band in config.bands:
        source = (
            Path(band.source).resolve() if band.source is not None else default_source.resolve()
        )
        LOGGER.info("Analyzing %s <- %s", band.name, source)
        if source not in decoded:
            decoded[source] = load_audio(source)
        try:
            signals.append(band_envelope(decoded[source], band, fps))
        except (ValueError, RuntimeError) as exc:
            raise BeatBloomError(f"Cannot analyze band {band.name!r} from {source}: {exc}") from exc
    return tuple(signals)
