"""Lazy Demucs API integration with FFmpeg stereo decoding and float32 stem output."""

from __future__ import annotations

import logging
import random
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import numpy as np
import soundfile as sf

from beatbloom.config import SAMPLE_RATE, SeparationConfig
from beatbloom.errors import BeatBloomError
from beatbloom.media import load_stereo

LOGGER = logging.getLogger(__name__)


class DemucsBackend:
    def versions(self) -> dict[str, str]:
        try:
            return {name: version(name) for name in ("demucs", "torch")}
        except PackageNotFoundError as exc:
            raise BeatBloomError(
                "Stem separation requires the demucs extra: uv sync --extra demucs "
                'or pip install "beatbloom[demucs]"'
            ) from exc

    def separate(self, audio: Path, destination: Path, config: SeparationConfig) -> dict[str, Path]:
        try:
            import torch
            from demucs.api import LoadModelError, Separator
        except (ImportError, OSError) as exc:
            raise BeatBloomError(f"Cannot import Demucs/PyTorch: {exc}") from exc
        device = config.device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        if device.startswith("cuda") and not torch.cuda.is_available():
            raise BeatBloomError(
                "CUDA is unavailable; install a CUDA-enabled PyTorch or use device=cpu"
            )
        LOGGER.info("Separating %s with %s on %s", audio, config.model, device)
        previous_random = random.getstate()
        random.seed(config.seed)
        paths: dict[str, Path] = {}
        try:
            devices = [torch.device(device).index or 0] if device.startswith("cuda") else []
            with torch.random.fork_rng(devices=devices):
                torch.manual_seed(config.seed)
                separator = Separator(
                    model=config.model,
                    device=device,
                    shifts=config.shifts,
                    overlap=config.overlap,
                    segment=config.segment,
                    jobs=config.jobs,
                    progress=LOGGER.isEnabledFor(logging.INFO),
                )
                if separator.samplerate != SAMPLE_RATE or separator.audio_channels != 2:
                    raise BeatBloomError("This backend expects a stereo 44100 Hz Demucs model")
                stereo = load_stereo(audio)
                with torch.inference_mode():
                    _, separated = separator.separate_tensor(torch.from_numpy(stereo), SAMPLE_RATE)
                for stem in config.stems:
                    if stem not in separated:
                        raise BeatBloomError(f"Demucs did not produce the required stem: {stem}")
                    samples = separated[stem].detach().cpu().numpy().T
                    if samples.shape != (stereo.shape[1], 2) or not np.all(np.isfinite(samples)):
                        raise BeatBloomError(f"Invalid or misaligned Demucs output for {stem}")
                    path = destination / f"{stem}.wav"
                    sf.write(path, samples, SAMPLE_RATE, subtype="FLOAT")
                    paths[stem] = path
        except (RuntimeError, ValueError, OSError, LoadModelError) as exc:
            raise BeatBloomError(f"Demucs separation failed: {exc}") from exc
        finally:
            random.setstate(previous_random)
        return paths
