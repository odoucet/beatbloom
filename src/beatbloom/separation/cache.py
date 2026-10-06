"""Reuse all model stems by audio content, backend versions and separation options."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

import soundfile as sf

from beatbloom.cache import CacheStore, file_hash, fingerprint, publish_directory, write_json
from beatbloom.config import SAMPLE_RATE, SeparationConfig
from beatbloom.errors import BeatBloomError
from beatbloom.media import require_file, require_tools
from beatbloom.separation.base import SeparationBackend, StemSet
from beatbloom.separation.demucs import DemucsBackend

LOGGER = logging.getLogger(__name__)
SEPARATION_VERSION = 1


def _inspect_stems(directory: Path, config: SeparationConfig) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    frames: int | None = None
    for stem in config.stems:
        path = directory / f"{stem}.wav"
        info = sf.info(path)
        if (
            info.samplerate != SAMPLE_RATE
            or info.channels != 2
            or info.frames <= 0
            or info.subtype != "FLOAT"
        ):
            raise ValueError(f"invalid stereo stem {stem}")
        if frames is not None and info.frames != frames:
            raise ValueError("stem lengths differ")
        frames = info.frames
        result[stem] = {"sha256": file_hash(path), "frames": frames, "sample_rate": SAMPLE_RATE}
    return result


def separate_audio(
    audio: Path,
    config: SeparationConfig | None = None,
    *,
    cache_dir: Path | None = None,
    refresh: bool = False,
    backend: SeparationBackend | None = None,
) -> StemSet:
    """Populate missing stems; reuse them without importing PyTorch on a cache hit."""
    require_tools()
    require_file(audio, "Audio")
    settings = config or SeparationConfig()
    selected = backend if backend is not None else DemucsBackend()
    store = CacheStore(cache_dir)
    audio_digest = file_hash(audio)
    parameters: dict[str, object] = {
        "separation_version": SEPARATION_VERSION,
        "audio_sha256": audio_digest,
        "versions": selected.versions(),
        "options": settings.model_dump(mode="json"),
    }
    key = fingerprint(parameters)
    destination = store.entry("stems", key)
    with store.locked("stems", key):
        if destination.exists() and not refresh:
            try:
                manifest = json.loads((destination / "manifest.json").read_text())
                metadata = _inspect_stems(destination, settings)
                if (
                    manifest["key"] != key
                    or manifest["parameters"] != parameters
                    or manifest["stems"] != metadata
                ):
                    raise ValueError("stem manifest does not match")
                LOGGER.info("Cache hit: stems/%s (%s)", key[:12], settings.model)
                return StemSet(
                    {stem: destination / f"{stem}.wav" for stem in settings.stems},
                    {stem: str(metadata[stem]["sha256"]) for stem in settings.stems},
                    destination / "manifest.json",
                    key,
                    True,
                )
            except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
                LOGGER.warning("Rebuilding invalid stem cache %s: %s", key[:12], exc)
        with tempfile.TemporaryDirectory(prefix=f".{key}-", dir=destination.parent) as name:
            staged = Path(name)
            paths = selected.separate(audio.resolve(), staged, settings)
            if set(paths) != set(settings.stems) or any(
                paths[stem].resolve() != (staged / f"{stem}.wav").resolve()
                for stem in settings.stems
            ):
                raise BeatBloomError(
                    "Separation backend returned an incomplete or invalid stem set"
                )
            try:
                metadata = _inspect_stems(staged, settings)
            except (OSError, RuntimeError, ValueError) as exc:
                raise BeatBloomError(f"Invalid separated audio: {exc}") from exc
            if file_hash(audio) != audio_digest:
                raise BeatBloomError("Audio changed during separation; retry with a stable input")
            write_json(
                staged / "manifest.json",
                {
                    "key": key,
                    "parameters": parameters,
                    "stems": metadata,
                },
            )
            publish_directory(staged, destination)
    return StemSet(
        {stem: destination / f"{stem}.wav" for stem in settings.stems},
        {stem: str(metadata[stem]["sha256"]) for stem in settings.stems},
        destination / "manifest.json",
        key,
        False,
    )
