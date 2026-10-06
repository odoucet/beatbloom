"""The prototype's CPU effects, applied to normalized RGB frames."""

from __future__ import annotations

import cv2
import numpy as np

from beatbloom.config import ProjectConfig
from beatbloom.models import EffectParameters, FloatArray, Signal

BLOOM_THRESHOLD = 0.55
BLOOM_SIGMA = 18.0
LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def parameters_at(
    config: ProjectConfig, signals: tuple[Signal, ...], timestamp: float
) -> EffectParameters:
    """Add effect weights across bands and multiply brightness mappings."""
    weights = {"bloom": 0.0, "exposure": 0.0, "saturation": 0.0, "zoom": 0.0}
    brightness = 1.0
    for band, signal in zip(config.bands, signals, strict=True):
        value = signal.at(timestamp)
        for effect, amount in band.effects.items():
            weights[effect] += value * amount
        if band.brightness is not None:
            dark, bright = band.brightness
            brightness *= dark + (bright - dark) * value
    return EffectParameters(
        bloom=weights["bloom"],
        exposure=weights["exposure"],
        saturation=weights["saturation"],
        zoom=weights["zoom"],
        brightness=brightness,
    )


def apply_effects(image: FloatArray, parameters: EffectParameters) -> FloatArray:
    """Return RGB float32 in 0..1 without modifying the input frame."""
    height, width = image.shape[:2]
    result = image.copy()
    if parameters.zoom > 1e-4:
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), 0, 1 + parameters.zoom)
        result = np.asarray(
            cv2.warpAffine(
                result,
                matrix,
                (width, height),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REFLECT,
            ),
            dtype=np.float32,
        )
    if abs(parameters.brightness - 1) > 1e-4:
        result = result * parameters.brightness
    if parameters.exposure > 1e-4:
        result = result * (1 + parameters.exposure)
    if parameters.saturation > 1e-4:
        luminance = np.asarray(result @ LUMA, dtype=np.float32)[..., None]
        result = luminance + (result - luminance) * (1 + parameters.saturation)
    if parameters.bloom > 1e-4:
        luminance = result @ LUMA
        mask = np.clip((luminance - BLOOM_THRESHOLD) / (1 - BLOOM_THRESHOLD), 0, 1)[..., None]
        small = cv2.resize(
            result * mask,
            (max(1, width // 4), max(1, height // 4)),
            interpolation=cv2.INTER_AREA,
        )
        small = cv2.GaussianBlur(small, (0, 0), BLOOM_SIGMA / 4)
        result = result + cv2.resize(small, (width, height)) * parameters.bloom
    return np.asarray(np.clip(result, 0, 1), dtype=np.float32)
