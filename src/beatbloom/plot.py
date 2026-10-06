"""Optional analysis plots; importing the base package does not require Matplotlib."""

from __future__ import annotations

import logging
import os
import tempfile
import warnings
from pathlib import Path

import librosa
import numpy as np

from beatbloom.config import ProjectConfig
from beatbloom.errors import BeatBloomError
from beatbloom.models import AudioTrack, Signal

LOGGER = logging.getLogger(__name__)


def save_plot(
    path: Path,
    track: AudioTrack,
    config: ProjectConfig,
    signals: tuple[Signal, ...],
    start: float,
    duration: float,
    overwrite: bool = False,
) -> None:
    """Plot the selected spectrogram and globally normalized signals on absolute time."""
    try:
        import matplotlib
    except ImportError as exc:
        raise BeatBloomError(
            'Plotting requires the plot extra: pip install "beatbloom[plot]" '
            "or uv sync --extra plot"
        ) from exc
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    segment = track.samples[
        int(start * track.sample_rate) : int((start + duration) * track.sample_rate)
    ]
    if len(segment) == 0:
        raise BeatBloomError("Default analysis source has no audio in the plotted excerpt")
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="n_fft=.*is too large", category=UserWarning)
        spectrum = librosa.amplitude_to_db(
            np.abs(librosa.stft(segment, n_fft=4096, hop_length=512)), ref=np.max
        )
    figure, (spectrogram, envelopes) = plt.subplots(2, 1, figsize=(16, 8))
    descriptor, filename = tempfile.mkstemp(
        prefix=".beatbloom-plot-", suffix=path.suffix, dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(filename)
    try:
        spectrogram.imshow(
            spectrum,
            origin="lower",
            aspect="auto",
            extent=(start, start + duration, 0, track.sample_rate / 2),
            vmin=-80,
            vmax=0,
        )
        spectrogram.set_yscale("log")
        spectrogram.set_ylim(20, track.sample_rate / 2)
        spectrogram.set_ylabel("Frequency (Hz)")
        spectrogram.set_title("Default analysis source (per-band source files may differ)")
        timestamps = np.linspace(start, start + duration, max(2, int(duration * 60) + 1))
        for band, signal in zip(config.bands, signals, strict=True):
            for cutoff in (band.low, band.high):
                if cutoff:
                    spectrogram.axhline(cutoff, ls="--", lw=1, color="white")
            envelopes.plot(
                timestamps,
                [signal.at(float(t)) for t in timestamps],
                label=f"{band.name} ({band.feature})",
            )
        envelopes.set_ylim(0, 1.05)
        envelopes.set_xlim(start, start + duration)
        envelopes.set_xlabel("Time in track (s)")
        envelopes.legend(loc="upper right")
        envelopes.set_title("Envelopes normalized on the complete source tracks")
        figure.tight_layout()
        figure.savefig(temporary, dpi=110)
        if path.exists() and not overwrite:
            raise BeatBloomError(f"Plot output already exists: {path}")
        os.replace(temporary, path)
    finally:
        plt.close(figure)
        temporary.unlink(missing_ok=True)
    LOGGER.info("Saved analysis plot: %s", path)
