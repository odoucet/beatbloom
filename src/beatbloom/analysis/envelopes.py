"""Percentile normalization, gating, gamma and attack/release smoothing."""

from __future__ import annotations

import numpy as np

from beatbloom.config import BandConfig
from beatbloom.models import FloatArray


def normalize(values: FloatArray, band: BandConfig) -> FloatArray:
    """Normalize on the complete track and explicitly leave silence at zero."""
    if len(values) == 0 or float(np.max(values)) <= 1e-9:
        return np.zeros_like(values)
    if band.feature == "loudness":
        # This is RMS expressed in dB, not an EBU R128 / LUFS measurement.
        db = 20 * np.log10(values.astype(np.float64) + 1e-9)
        floor = float(np.percentile(db, band.floor_percentile))
        reference = float(np.percentile(db, band.reference))
        normalized = (db - floor) / max(1e-6, reference - floor)
    else:
        reference = float(np.percentile(values, band.reference)) or 1.0
        normalized = values.astype(np.float64) / reference
    normalized = np.clip(normalized, 0, 1)
    normalized = np.clip((normalized - band.gate) / (1 - band.gate), 0, 1) ** band.gamma
    return np.asarray(normalized, dtype=np.float32)


def smooth(values: FloatArray, band: BandConfig, fps: float) -> FloatArray:
    """Use separate time constants for rising and falling energy."""
    if len(values) == 0:
        return values.copy()
    attack = np.exp(-1.0 / max(1e-6, band.attack_ms / 1000 * fps))
    release = np.exp(-1.0 / max(1e-6, band.release_ms / 1000 * fps))
    result = np.empty_like(values)
    previous = float(values[0]) if band.feature == "loudness" else 0.0
    for index, value in enumerate(values):
        coefficient = attack if value > previous else release
        previous = float(coefficient * previous + (1 - coefficient) * value)
        result[index] = previous
    return result
