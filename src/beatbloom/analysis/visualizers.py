"""Full-track peaks and blockwise STFT bands, with independent display-free caches."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

import numpy as np
from scipy.fft import rfft, rfftfreq
from scipy.signal.windows import hann

from beatbloom.analysis.cache import AnalysisCache
from beatbloom.analysis.features import HOP_LENGTH
from beatbloom.cache import CacheStore, fingerprint
from beatbloom.config import SAMPLE_RATE, SpectrumConfig, VisualizerConfig, WaveformConfig
from beatbloom.models import AudioTrack, FeatureSeries, FloatArray

LOGGER = logging.getLogger(__name__)
VISUALIZER_VERSION = 1
FFT_BLOCK_FRAMES = 512


def extract_waveform(track: AudioTrack) -> FeatureSeries:
    """Retain signed min/max PCM peaks in every native hop, including the final partial hop."""
    samples = track.samples
    count, remainder = divmod(len(samples), HOP_LENGTH)
    values = np.empty((count + bool(remainder), 2), dtype=np.float32)
    if count:
        blocks = samples[: count * HOP_LENGTH].reshape(count, HOP_LENGTH)
        values[:count, 0] = blocks.min(axis=1)
        values[:count, 1] = blocks.max(axis=1)
    if remainder:
        values[-1] = samples[-remainder:].min(), samples[-remainder:].max()
    times = np.arange(len(values), dtype=np.float64) * HOP_LENGTH / SAMPLE_RATE
    return FeatureSeries(times, values, track.duration)


def normalize_waveform(series: FeatureSeries, config: WaveformConfig) -> FeatureSeries:
    reference = float(np.percentile(np.max(np.abs(series.values), axis=1), config.ref_percentile))
    values = (
        np.clip(series.values / reference, -1, 1)
        if reference > 1e-9
        else np.zeros_like(series.values)
    )
    return FeatureSeries(series.timestamps, np.asarray(values, dtype=np.float32), series.duration)


def logarithmic_weights(config: SpectrumConfig) -> FloatArray:
    """Mean power per log band; interpolate narrow bands that contain no FFT bin."""
    frequencies = np.asarray(rfftfreq(config.n_fft, 1 / SAMPLE_RATE), dtype=np.float64)
    edges = np.geomspace(config.low, config.high, config.bands + 1)
    weights = np.zeros((len(frequencies), config.bands), dtype=np.float32)
    for index, (low, high) in enumerate(zip(edges[:-1], edges[1:], strict=True)):
        bins = np.flatnonzero((frequencies >= low) & (frequencies < high))
        if len(bins):
            weights[bins, index] = 1 / len(bins)
        else:
            center = np.sqrt(low * high)
            right = min(int(np.searchsorted(frequencies, center)), len(frequencies) - 1)
            left = max(0, right - 1)
            fraction = float(
                (center - frequencies[left]) / (frequencies[right] - frequencies[left])
            )
            weights[left, index] = 1 - fraction
            weights[right, index] = fraction
    return weights


def extract_spectrum(track: AudioTrack, config: SpectrumConfig) -> FeatureSeries:
    """Bound FFT memory to one block; cache only the log bands, never a full-track STFT."""
    samples = track.samples
    count = len(samples) // HOP_LENGTH + 1
    values = np.empty((count, config.bands), dtype=np.float32)
    weights = logarithmic_weights(config)
    window = np.asarray(hann(config.n_fft, sym=False), dtype=np.float32)
    scale = np.float32(2 / window.sum())
    half = config.n_fft // 2
    for begin in range(0, count, FFT_BLOCK_FRAMES):
        end = min(count, begin + FFT_BLOCK_FRAMES)
        left, right = begin * HOP_LENGTH - half, (end - 1) * HOP_LENGTH + half
        segment = samples[max(0, left) : min(len(samples), right)]
        if left < 0 or right > len(samples):
            segment = np.pad(segment, (max(0, -left), max(0, right - len(samples))))
        frames = np.lib.stride_tricks.sliding_window_view(segment, config.n_fft)[::HOP_LENGTH]
        transformed = rfft(frames * window, axis=1, workers=1) * scale
        power = np.asarray(np.abs(transformed) ** 2, dtype=np.float32)
        values[begin:end] = np.sqrt(np.maximum(power @ weights, 0))
        LOGGER.debug("Spectrum frames: %s/%s", end, count)
    times = np.arange(count, dtype=np.float64) * HOP_LENGTH / SAMPLE_RATE
    return FeatureSeries(times, values, track.duration)


def normalize_spectrum(series: FeatureSeries, config: SpectrumConfig) -> FeatureSeries:
    """Normalize the complete track in dB, then smooth each native-frequency envelope."""
    reference = float(np.percentile(series.values, config.ref_percentile))
    if reference <= 1e-9:
        return FeatureSeries(series.timestamps, np.zeros_like(series.values), series.duration)
    ratio = np.maximum(series.values / reference, np.finfo(np.float32).tiny)
    values = np.asarray(
        np.clip((20 * np.log10(ratio) - config.floor_db) / -config.floor_db, 0, 1) ** config.gamma,
        dtype=np.float32,
    )
    rate = SAMPLE_RATE / HOP_LENGTH
    attack = np.exp(-1 / max(1e-6, config.attack_ms / 1000 * rate))
    release = np.exp(-1 / max(1e-6, config.release_ms / 1000 * rate))
    previous = np.zeros(values.shape[1], dtype=np.float64)
    for index in range(len(values)):
        coefficients = np.where(values[index] > previous, attack, release)
        previous = coefficients * previous + (1 - coefficients) * values[index]
        values[index] = previous
    return FeatureSeries(series.timestamps, values, series.duration)


@dataclass(frozen=True)
class VisualizerAnalysis:
    series: dict[str, tuple[FeatureSeries, ...]]
    keys: dict[str, tuple[str, ...]]
    hits: int
    feature_hits: int


def analyze_visualizers(
    definitions: Mapping[str, VisualizerConfig],
    sources: Mapping[str, tuple[Path, ...]],
    hashes: Mapping[Path, str],
    load_track: Callable[[Path], AudioTrack],
    store: CacheStore,
    *,
    refresh: bool = False,
) -> VisualizerAnalysis:
    cache = AnalysisCache(store)
    versions = {name: version(name) for name in ("numpy", "scipy")}
    data: dict[str, tuple[FeatureSeries, ...]] = {}
    keys: dict[str, tuple[str, ...]] = {}
    hits = feature_hits = 0
    refreshed_features: set[str] = set()
    refreshed_envelopes: set[str] = set()
    for name, config in definitions.items():
        series_list: list[FeatureSeries] = []
        key_list: list[str] = []
        for source in sources[name]:
            waveform = config.type == "waveform"
            columns = 2 if waveform else config.spectrum.bands
            raw_parameters: dict[str, object] = {
                "visualizer_version": VISUALIZER_VERSION,
                "versions": versions,
                "audio_sha256": hashes[source],
                "kind": config.type,
                "sample_rate": SAMPLE_RATE,
                "hop_length": HOP_LENGTH,
            }
            if not waveform:
                raw_parameters["spectrum"] = config.spectrum.model_dump(
                    mode="json",
                    include={"n_fft", "bands", "low", "high"},
                )
            raw_key = fingerprint(raw_parameters)
            parameters: dict[str, object] = {
                "visualizer_version": VISUALIZER_VERSION,
                "kind": config.type,
                "feature_key": raw_key,
                "envelope": {"ref_percentile": config.waveform.ref_percentile}
                if waveform
                else config.spectrum.model_dump(
                    mode="json", exclude={"n_fft", "bands", "low", "high"}
                ),
            }
            key = fingerprint(parameters)

            def compute_envelope(
                source: Path = source,
                config: VisualizerConfig = config,
                raw_parameters: dict[str, object] = raw_parameters,
                raw_key: str = raw_key,
                columns: int = columns,
                waveform: bool = waveform,
            ) -> FeatureSeries:
                nonlocal feature_hits

                def compute_raw() -> FeatureSeries:
                    LOGGER.info("Extracting %s visualizer from %s", config.type, source)
                    track = load_track(source)
                    return (
                        extract_waveform(track)
                        if waveform
                        else extract_spectrum(track, config.spectrum)
                    )

                raw, hit = cache.get(
                    "visualizer_features",
                    raw_key,
                    raw_parameters,
                    compute_raw,
                    refresh=refresh and raw_key not in refreshed_features,
                    columns=columns,
                    signed=waveform,
                    extrema=waveform,
                )
                refreshed_features.add(raw_key)
                feature_hits += int(hit)
                return (
                    normalize_waveform(raw, config.waveform)
                    if waveform
                    else normalize_spectrum(raw, config.spectrum)
                )

            series, hit = cache.get(
                "visualizers",
                key,
                parameters,
                compute_envelope,
                refresh=refresh and key not in refreshed_envelopes,
                columns=columns,
                signed=waveform,
                extrema=waveform,
            )
            refreshed_envelopes.add(key)
            hits += int(hit)
            series_list.append(series)
            key_list.append(key)
        data[name] = tuple(series_list)
        keys[name] = tuple(key_list)
    return VisualizerAnalysis(data, keys, hits, feature_hits)
