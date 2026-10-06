from __future__ import annotations

import json

import numpy as np
import pytest

from beatbloom.config import VisualizerConfig
from beatbloom.models import FeatureSeries
from beatbloom.render.visualizers import apply_visualizers, region


def test_opacity_colors_and_region_do_not_change_other_pixels_or_input() -> None:
    config = VisualizerConfig.model_validate_json(
        json.dumps(
            {
                "type": "spectrum",
                "left": 0,
                "width": 1,
                "height": 0.25,
                "bottom": 0,
                "opacity": 0.5,
                "background_opacity": 0,
                "bar_gap": 0,
                "tracks": [{"stem": "mix", "color": "#ff0000"}],
            }
        )
    )
    image = np.full((40, 80, 3), 0.2, dtype=np.float32)
    series = FeatureSeries(
        np.array([0, 0.5], dtype=np.float64), np.ones((2, 64), dtype=np.float32), 1.0
    )
    result = apply_visualizers(image, {"spectrum": config}, {"spectrum": (series,)}, 0.25)
    np.testing.assert_array_equal(image, np.float32(0.2))
    np.testing.assert_array_equal(result[:30], image[:30])
    np.testing.assert_allclose(result[30:, :, 0], 0.6)
    np.testing.assert_allclose(result[30:, :, 1:], 0.1)


@pytest.mark.parametrize("kind", ["waveform", "spectrum"])
@pytest.mark.parametrize("layout", ["overlay", "stacked", "side_by_side"])
@pytest.mark.parametrize("shape", [(2, 2), (48, 64)])
def test_multi_track_layouts_are_finite_and_clipped(
    kind: str, layout: str, shape: tuple[int, int]
) -> None:
    config = VisualizerConfig.model_validate_json(
        json.dumps(
            {
                "type": kind,
                "layout": layout,
                "gain": 2,
                "tracks": [
                    {"stem": "drums", "color": "#ff6600"},
                    {"stem": "bass", "color": "#55ccff"},
                    {"stem": "other", "color": "#ee66cc"},
                ],
            }
        )
    )
    values = (
        np.array([[-0.5, 0.8], [-0.3, 0.5]], dtype=np.float32)
        if kind == "waveform"
        else np.ones((2, 64), dtype=np.float32)
    )
    series = FeatureSeries(np.array([0, 0.5], dtype=np.float64), values, 1.0)
    image = np.zeros((*shape, 3), dtype=np.float32)
    result = apply_visualizers(image, {"multi": config}, {"multi": (series,) * 3}, 0.25)
    assert result.shape == image.shape and result.dtype == np.float32
    assert np.all(np.isfinite(result)) and np.all((result >= 0) & (result <= 1))
    left, top, right, bottom = region(config, shape[1], shape[0])
    assert 0 <= left < right <= shape[1] and 0 <= top < bottom <= shape[0]


def test_absent_or_transparent_visualizers_are_identity() -> None:
    image = np.random.default_rng(4).random((12, 20, 3), dtype=np.float32)
    np.testing.assert_array_equal(apply_visualizers(image, {}, {}, 1), image)
    config = VisualizerConfig(type="spectrum", opacity=0.0)
    np.testing.assert_array_equal(apply_visualizers(image, {"hidden": config}, {}, 1), image)


def test_silent_or_finished_spectrum_draws_no_bars() -> None:
    config = VisualizerConfig(type="spectrum", background_opacity=0.0)
    image = np.full((40, 80, 3), 0.2, dtype=np.float32)
    for values, timestamp in (
        (np.zeros((2, 64), dtype=np.float32), 0.25),
        (np.ones((2, 64), dtype=np.float32), 1.0),
    ):
        series = FeatureSeries(np.array([0, 0.5], dtype=np.float64), values, 1.0)
        np.testing.assert_array_equal(
            apply_visualizers(image, {"music": config}, {"music": (series,)}, timestamp), image
        )
