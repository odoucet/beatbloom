"""Frequency isolation before feature extraction."""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt

from beatbloom.config import NYQUIST, SAMPLE_RATE, BandConfig
from beatbloom.models import FloatArray


def filter_band(samples: FloatArray, band: BandConfig) -> FloatArray:
    """Apply a fourth-order Butterworth filter, including short and edge-band inputs."""
    low = band.low or 0.0
    high = band.high if band.high is not None else NYQUIST
    if low == 0 and high == NYQUIST:
        return samples
    if low == 0:
        sos = butter(4, high, btype="lowpass", fs=SAMPLE_RATE, output="sos")
    elif high == NYQUIST:
        sos = butter(4, low, btype="highpass", fs=SAMPLE_RATE, output="sos")
    else:
        sos = butter(4, [low, high], btype="bandpass", fs=SAMPLE_RATE, output="sos")
    # Match SciPy's default padding when possible; tiny clips must not fail.
    padlen = 3 * (2 * len(sos) + 1 - min((sos[:, 2] == 0).sum(), (sos[:, 5] == 0).sum()))
    filtered = sosfiltfilt(sos, samples, padlen=min(int(padlen), len(samples) - 1))
    return np.asarray(filtered, dtype=np.float32)
