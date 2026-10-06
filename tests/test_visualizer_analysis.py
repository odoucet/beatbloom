from __future__ import annotations

import numpy as np
import pytest

from beatbloom.analysis.features import HOP_LENGTH
from beatbloom.analysis.visualizers import (
    extract_spectrum,
    extract_waveform,
    logarithmic_weights,
    normalize_spectrum,
    normalize_waveform,
)
from beatbloom.config import SAMPLE_RATE, SpectrumConfig, WaveformConfig
from beatbloom.models import AudioTrack, FeatureSeries
from beatbloom.render.visualizers import spectrum_at, waveform_window


@pytest.mark.parametrize("samples", [1, 16, 256, 257, 44100])
def test_peaks_cover_short_audio_partial_hops_and_silence(samples: int) -> None:
    track = AudioTrack(np.zeros(samples, dtype=np.float32), SAMPLE_RATE)
    series = extract_waveform(track)
    assert series.values.shape == ((samples + HOP_LENGTH - 1) // HOP_LENGTH, 2)
    assert series.duration == samples / SAMPLE_RATE
    np.testing.assert_array_equal(normalize_waveform(series, WaveformConfig()).values, 0)


def test_signed_peaks_and_full_track_normalization(track: AudioTrack) -> None:
    series = normalize_waveform(extract_waveform(track), WaveformConfig())
    assert series.values.shape[1] == 2
    assert np.all(series.values[:, 0] <= series.values[:, 1])
    assert np.max(np.abs(series.values[20:100])) < 0.3
    assert np.max(np.abs(series.values[200:300])) > 0.9


@pytest.mark.parametrize("samples", [1, 16, 257, 44100])
def test_short_spectrum_and_silence(samples: int) -> None:
    track = AudioTrack(np.zeros(samples, dtype=np.float32), SAMPLE_RATE)
    config = SpectrumConfig(bands=32)
    raw = extract_spectrum(track, config)
    assert raw.values.shape == (samples // HOP_LENGTH + 1, 32)
    assert np.all(np.isfinite(raw.values))
    np.testing.assert_array_equal(normalize_spectrum(raw, config).values, 0)


def test_log_bands_locate_a_tone_and_interpolate_narrow_bins() -> None:
    times = np.arange(SAMPLE_RATE, dtype=np.float32) / SAMPLE_RATE
    track = AudioTrack(np.sin(2 * np.pi * 1000 * times).astype(np.float32), SAMPLE_RATE)
    config = SpectrumConfig(bands=64, n_fft=4096)
    raw = extract_spectrum(track, config)
    winner = int(np.argmax(np.mean(raw.values[10:-10], axis=0)))
    edges = np.geomspace(config.low, config.high, config.bands + 1)
    assert edges[winner] <= 1000 < edges[winner + 1]
    weights = logarithmic_weights(SpectrumConfig(n_fft=256, bands=256))
    np.testing.assert_allclose(weights.sum(axis=0), 1, rtol=1e-6)
    assert np.all(np.isfinite(weights))


def test_fft_block_boundaries_do_not_change_the_result(monkeypatch: pytest.MonkeyPatch) -> None:
    from beatbloom.analysis import visualizers

    track = AudioTrack(
        np.random.default_rng(5).normal(0, 0.1, 12000).astype(np.float32), SAMPLE_RATE
    )
    config = SpectrumConfig(n_fft=512, bands=16)
    first = extract_spectrum(track, config)
    monkeypatch.setattr(visualizers, "FFT_BLOCK_FRAMES", 3)
    blocked = extract_spectrum(track, config)
    np.testing.assert_allclose(blocked.values, first.values, rtol=1e-6, atol=1e-7)
    np.testing.assert_array_equal(blocked.timestamps, first.timestamps)


def test_native_spectrum_smoothing_interpolation_and_source_end() -> None:
    times = np.arange(3, dtype=np.float64) * HOP_LENGTH / SAMPLE_RATE
    raw = FeatureSeries(times, np.array([[1, 0], [1, 0], [0, 0]], dtype=np.float32), 0.02)
    config = SpectrumConfig(attack_ms=10.0, release_ms=1000.0, ref_percentile=100.0)
    series = normalize_spectrum(raw, config)
    assert 0 < series.values[0, 0] < series.values[1, 0] < 1
    assert series.values[2, 0] > series.values[1, 0] * 0.98
    np.testing.assert_allclose(
        spectrum_at(series, times[1] / 2), (series.values[0] + series.values[1]) / 2
    )
    np.testing.assert_array_equal(spectrum_at(series, -1), 0)
    np.testing.assert_array_equal(spectrum_at(series, 0.02), 0)


def test_downsampled_waveform_preserves_a_brief_transient() -> None:
    values = np.zeros((100, 2), dtype=np.float32)
    values[47] = -0.9, 1.0
    series = FeatureSeries(np.arange(100, dtype=np.float64) * 0.01, values, 1.0)
    peaks = waveform_window(series, 0.5, 1.0, 2)
    assert np.min(peaks[:, 0]) == pytest.approx(-0.9)
    assert np.max(peaks[:, 1]) == 1
    np.testing.assert_array_equal(waveform_window(series, -2, 1.0, 10), 0)
    np.testing.assert_array_equal(waveform_window(series, 3, 1.0, 10), 0)
