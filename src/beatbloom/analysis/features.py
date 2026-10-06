"""Native timestamped audio features, independent of every video setting."""

from __future__ import annotations

import warnings

import librosa
import numpy as np

from beatbloom.analysis.envelopes import normalize, smooth
from beatbloom.analysis.filters import filter_band
from beatbloom.config import SAMPLE_RATE, SignalConfig
from beatbloom.errors import BeatBloomError
from beatbloom.models import AudioTrack, FeatureSeries, Signal

HOP_LENGTH = 256
FRAME_LENGTH = 2048
FEATURE_RATE = SAMPLE_RATE / HOP_LENGTH
ANALYSIS_VERSION = 2


def extract_features(track: AudioTrack, config: SignalConfig) -> FeatureSeries:
    """Extract complete-track onset strength or RMS on the fixed audio hop grid."""
    if track.sample_rate != SAMPLE_RATE or not len(track.samples):
        raise BeatBloomError(f"Analysis requires nonempty {SAMPLE_RATE} Hz PCM")
    samples = filter_band(track.samples, config)
    if config.feature == "onset":
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="n_fft=.*is too large", category=UserWarning)
            features = librosa.onset.onset_strength(
                y=samples,
                sr=SAMPLE_RATE,
                hop_length=HOP_LENGTH,
                n_fft=FRAME_LENGTH,
            )
    else:
        features = librosa.feature.rms(
            y=samples,
            frame_length=FRAME_LENGTH,
            hop_length=HOP_LENGTH,
        )[0]
    times = np.arange(len(features), dtype=np.float64) * HOP_LENGTH / SAMPLE_RATE
    return FeatureSeries(times, np.asarray(features, dtype=np.float32), track.duration)


def make_envelope(features: FeatureSeries, config: SignalConfig) -> FeatureSeries:
    values = smooth(normalize(features.values, config), config, FEATURE_RATE)
    return FeatureSeries(features.timestamps, values, features.duration)


def signal_from_track(name: str, track: AudioTrack, config: SignalConfig) -> Signal:
    """Convenience API for in-memory analysis without persistent caching."""
    envelope = make_envelope(extract_features(track, config), config)
    return Signal(name, envelope.values, envelope.timestamps, envelope.duration)
