from __future__ import annotations

import numpy as np
import pytest

from beatbloom.config import BandConfig, ProjectConfig
from beatbloom.models import EffectParameters, Signal
from beatbloom.render.effects import apply_effects, parameters_at


def test_no_effect_is_identity_and_does_not_mutate_input() -> None:
    image = np.random.default_rng(3).random((8, 12, 3), dtype=np.float32)
    result = apply_effects(image, EffectParameters())
    np.testing.assert_array_equal(result, image)
    assert not np.shares_memory(result, image)


def test_brightness_and_exposure_are_multiplicative() -> None:
    image = np.full((4, 4, 3), 0.4, dtype=np.float32)
    result = apply_effects(image, EffectParameters(brightness=0.5, exposure=0.25))
    np.testing.assert_allclose(result, 0.25)


def test_saturation_preserves_gray() -> None:
    image = np.full((4, 4, 3), 0.4, dtype=np.float32)
    np.testing.assert_allclose(apply_effects(image, EffectParameters(saturation=2.0)), image)


def test_bloom_changes_highlights_but_not_dark_frames() -> None:
    dark = np.full((8, 8, 3), 0.2, dtype=np.float32)
    bright = np.full((8, 8, 3), 0.8, dtype=np.float32)
    parameters = EffectParameters(bloom=0.3)
    np.testing.assert_allclose(apply_effects(dark, parameters), dark)
    assert np.mean(apply_effects(bright, parameters)) > np.mean(bright)


def test_tiny_frame_with_all_effects_is_finite_and_clipped() -> None:
    image = np.full((2, 2, 3), 0.8, dtype=np.float32)
    parameters = EffectParameters(bloom=2, zoom=0.1, saturation=2, exposure=2)
    result = apply_effects(image, parameters)
    assert result.shape == image.shape
    assert result.dtype == np.float32
    assert np.all(np.isfinite(result))
    assert np.all((result >= 0) & (result <= 1))


def test_mapping_adds_effects_and_multiplies_brightness() -> None:
    config = ProjectConfig(
        bands=(
            BandConfig(name="a", effects={"bloom": 2.0}, brightness=(0.4, 1.0)),
            BandConfig(name="b", effects={"bloom": 1.0}, brightness=(0.5, 1.0)),
        )
    )
    signals = tuple(
        Signal(name, np.array([0.5, 0.5], dtype=np.float32), 1.0, 2.0) for name in ("a", "b")
    )
    result = parameters_at(config, signals, 0.0)
    assert result.bloom == 1.5
    assert result.brightness == pytest.approx(0.7 * 0.75)
