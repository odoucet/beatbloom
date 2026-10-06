"""Shared full-track analysis pipeline for standalone analysis, preview and final render."""

from __future__ import annotations

import logging
from importlib.metadata import version
from pathlib import Path

from beatbloom.analysis.cache import AnalysisCache
from beatbloom.analysis.features import (
    ANALYSIS_VERSION,
    FRAME_LENGTH,
    HOP_LENGTH,
    extract_features,
    make_envelope,
)
from beatbloom.cache import CacheStore, file_hash, fingerprint, write_json
from beatbloom.config import SAMPLE_RATE, ProjectConfig, SignalConfig
from beatbloom.errors import BeatBloomError
from beatbloom.media import audio_duration, load_audio, require_file, require_tools
from beatbloom.models import AnalysisResult, AudioTrack, FeatureSeries, Signal
from beatbloom.separation.base import SeparationBackend
from beatbloom.separation.cache import separate_audio

LOGGER = logging.getLogger(__name__)


def analyze(
    audio: Path,
    config: ProjectConfig,
    *,
    drive: Path | None = None,
    cache_dir: Path | None = None,
    refresh: bool = False,
    backend: SeparationBackend | None = None,
) -> AnalysisResult:
    """Resolve only required stems and reuse raw features or complete signal envelopes."""
    require_tools()
    audio = audio.resolve()
    require_file(audio, "Audio")
    if drive is not None:
        require_file(drive, "Default analysis source")
    for specification in config.signals.values():
        if specification.source is not None:
            require_file(Path(specification.source), "Signal source")
    store = CacheStore(cache_dir)
    cache = AnalysisCache(store)
    hashes = {audio: file_hash(audio)}
    duration = audio_duration(audio)
    stems = None
    if any(signal.stem not in (None, "mix") for signal in config.signals.values()):
        stems = separate_audio(
            audio,
            config.separation,
            cache_dir=store.root,
            refresh=refresh,
            backend=backend,
        )
        hashes.update({stems.stems[name]: value for name, value in stems.hashes.items()})
    sources: dict[str, Path] = {}
    for name, specification in config.signals.items():
        if specification.source is not None:
            source = Path(specification.source).resolve()
        elif specification.stem == "mix":
            source = audio
        elif specification.stem is not None:
            assert stems is not None
            source = stems.stems[specification.stem]
        else:
            source = (drive or audio).resolve()
        sources[name] = source
        if source not in hashes:
            hashes[source] = file_hash(source)
    tracks: dict[Path, AudioTrack] = {}
    signals: dict[str, Signal] = {}
    signal_keys: dict[str, str] = {}
    signal_hits = 0
    feature_hits = 0
    versions = {name: version(name) for name in ("librosa", "scipy", "numpy")}

    for name, specification in config.signals.items():
        source = sources[name]
        feature_parameters: dict[str, object] = {
            "analysis_version": ANALYSIS_VERSION,
            "versions": versions,
            "audio_sha256": hashes[source],
            "sample_rate": SAMPLE_RATE,
            "hop_length": HOP_LENGTH,
            "frame_length": FRAME_LENGTH,
            "low": specification.low,
            "high": specification.high,
            "feature": "onset" if specification.feature == "onset" else "rms",
        }
        feature_key = fingerprint(feature_parameters)
        signal_parameters: dict[str, object] = {
            "analysis_version": ANALYSIS_VERSION,
            "feature_key": feature_key,
            "envelope": specification.model_dump(mode="json", exclude={"source", "stem"}),
        }
        signal_key = fingerprint(signal_parameters)

        def compute_signal(
            source: Path = source,
            specification: SignalConfig = specification,
            feature_parameters: dict[str, object] = feature_parameters,
            feature_key: str = feature_key,
        ) -> FeatureSeries:
            nonlocal feature_hits

            def compute_features() -> FeatureSeries:
                LOGGER.info("Extracting %s from %s", specification.feature, source)
                if source not in tracks:
                    tracks[source] = load_audio(source)
                    if file_hash(source) != hashes[source]:
                        raise BeatBloomError(
                            "Audio changed during analysis; retry with a stable input"
                        )
                return extract_features(tracks[source], specification)

            features, hit = cache.get(
                "features",
                feature_key,
                feature_parameters,
                compute_features,
                refresh=refresh,
            )
            feature_hits += int(hit)
            return make_envelope(features, specification)

        envelope, hit = cache.get(
            "signals",
            signal_key,
            signal_parameters,
            compute_signal,
            refresh=refresh,
        )
        signal_hits += int(hit)
        signals[name] = Signal(name, envelope.values, envelope.timestamps, envelope.duration)
        signal_keys[name] = signal_key
        if source == audio:
            duration = envelope.duration

    bundle_parameters: dict[str, object] = {
        "analysis_version": ANALYSIS_VERSION,
        "audio_sha256": hashes[audio],
        "signals": signal_keys,
    }
    bundle_key = fingerprint(bundle_parameters)
    manifest = store.entry("analysis", bundle_key).with_suffix(".json")
    write_json(
        manifest,
        {
            "key": bundle_key,
            "parameters": bundle_parameters,
            "audio_duration": duration,
            "signals": {
                name: {
                    "source": str(sources[name]),
                    "key": key,
                    "series": str(store.entry("signals", key) / "series.npz"),
                }
                for name, key in signal_keys.items()
            },
            "stems_manifest": str(stems.manifest) if stems is not None else None,
        },
    )
    LOGGER.info("Analysis ready: %s/%s signal cache hits; %s", signal_hits, len(signals), manifest)
    return AnalysisResult(
        signals,
        manifest,
        duration,
        signal_hits,
        feature_hits,
        stems.cached if stems is not None else None,
    )
