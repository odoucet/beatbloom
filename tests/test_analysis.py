from __future__ import annotations

import math

import numpy as np
import pytest

from beatbloom.analysis.envelopes import normalize, smooth
from beatbloom.analysis.features import signal_from_track
from beatbloom.analysis.filters import filter_band
from beatbloom.config import SAMPLE_RATE, SignalConfig
from beatbloom.models import AudioTrack, Signal


@pytest.mark.parametrize("feature", ["onset", "rms", "loudness"])
def test_silence_stays_zero(feature: str) -> None:
    band = SignalConfig.model_validate_json(f'{{"feature":"{feature}"}}')
    track = AudioTrack(np.zeros(SAMPLE_RATE, dtype=np.float32), SAMPLE_RATE)
    signal = signal_from_track("silence", track, band)
    assert np.all(signal.values == 0)


def test_rms_responds_to_energy_and_excerpt_keeps_full_track_normalization(
    track: AudioTrack,
) -> None:
    band = SignalConfig(feature="rms", attack_ms=0.0, release_ms=0.0)
    full = signal_from_track("energy", track, band)
    assert full.at(0.5) < full.at(1.5) * 0.3
    # Sampling a preview from the same full signal preserves its relative amplitude.
    assert 0 < full.at(0.5) < 0.3
    cropped = signal_from_track(
        "cropped", AudioTrack(track.samples[:SAMPLE_RATE], SAMPLE_RATE), band
    )
    assert cropped.at(0.5) > 0.9


def test_attack_and_release_have_distinct_time_constants() -> None:
    values = np.array([1.0, 1.0, 0.0], dtype=np.float32)
    band = SignalConfig(attack_ms=10.0, release_ms=1000.0)
    result = smooth(values, band, 100.0)
    assert result[0] == pytest.approx(1 - math.exp(-1), rel=1e-6)
    assert result[2] > result[1] * 0.98
    assert result[2] < result[1]


def test_loudness_initializes_from_first_frame() -> None:
    band = SignalConfig(feature="loudness")
    values = np.array([0.8, 0.8], dtype=np.float32)
    np.testing.assert_allclose(smooth(values, band, 30.0), values)


def test_gate_and_gamma() -> None:
    band = SignalConfig(feature="rms", ref_percentile=100.0, gate=0.5, gamma=2.0)
    result = normalize(np.array([0.0, 0.5, 0.75, 1.0], dtype=np.float32), band)
    np.testing.assert_allclose(result, [0, 0, 0.25, 1])


def test_empty_envelopes_are_safe() -> None:
    values = np.array([], dtype=np.float32)
    band = SignalConfig()
    assert len(normalize(values, band)) == 0
    assert len(smooth(values, band, 30.0)) == 0


def test_frequency_filter_rejects_out_of_band_tone() -> None:
    times = np.arange(SAMPLE_RATE, dtype=np.float32) / SAMPLE_RATE
    band = SignalConfig(low=40.0, high=120.0)
    inside = filter_band(np.sin(2 * np.pi * 80 * times).astype(np.float32), band)[1000:-1000]
    outside = filter_band(np.sin(2 * np.pi * 3000 * times).astype(np.float32), band)[1000:-1000]
    assert np.mean(inside**2) > np.mean(outside**2) * 1000


@pytest.mark.parametrize(
    "cutoffs",
    [
        {"low": 40.0, "high": 120.0},
        {"high": 120.0},
        {"low": 400.0},
        {},
    ],
)
def test_short_audio_and_edge_filters(cutoffs: dict[str, float]) -> None:
    band = SignalConfig(feature="rms", **cutoffs)
    track = AudioTrack(np.ones(16, dtype=np.float32), SAMPLE_RATE)
    signal = signal_from_track("energy", track, band)
    assert np.all(np.isfinite(signal.values))
    assert np.all((signal.values >= 0) & (signal.values <= 1))


def test_signal_interpolation_and_source_end() -> None:
    signal = Signal(
        "kick", np.array([0, 1, 0], dtype=np.float32), np.array([0, 0.5, 1], dtype=np.float64), 1.0
    )
    assert signal.at(0.25) == 0.5
    assert signal.at(-1) == 0
    assert signal.at(1) == 0
