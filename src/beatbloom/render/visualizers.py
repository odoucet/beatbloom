"""Responsive RGB overlays using cached peaks and frequency envelopes only."""

from __future__ import annotations

from collections.abc import Mapping

import cv2
import numpy as np

from beatbloom.config import VisualizerConfig
from beatbloom.models import FeatureSeries, FloatArray, PixelArray

Bounds = tuple[int, int, int, int]


def color_rgb(color: str) -> FloatArray:
    return np.array(
        [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)], dtype=np.float32
    )


def spectrum_at(series: FeatureSeries, timestamp: float) -> FloatArray:
    if timestamp < 0 or timestamp >= series.duration:
        return np.zeros(series.values.shape[1], dtype=np.float32)
    right = int(np.searchsorted(series.timestamps, timestamp, side="right"))
    if right == 0:
        return np.asarray(series.values[0], dtype=np.float32).copy()
    if right == len(series.timestamps):
        return np.asarray(series.values[-1], dtype=np.float32).copy()
    left = right - 1
    fraction = (timestamp - series.timestamps[left]) / (
        series.timestamps[right] - series.timestamps[left]
    )
    return np.asarray(
        series.values[left] * (1 - fraction) + series.values[right] * fraction, dtype=np.float32
    )


def waveform_window(
    series: FeatureSeries, timestamp: float, window: float, points: int
) -> FloatArray:
    """Resample a centered window without dropping transients when pixels cover several hops."""
    edges = np.linspace(timestamp - window / 2, timestamp + window / 2, points + 1)
    centers = (edges[:-1] + edges[1:]) / 2
    result = np.column_stack(
        [
            np.interp(centers, series.timestamps, series.values[:, index], left=0, right=0)
            for index in range(2)
        ]
    ).astype(np.float32)
    indices = np.searchsorted(series.timestamps, edges)
    occupied = np.flatnonzero(np.diff(indices) > 0)
    if len(occupied):
        begin, end = int(indices[0]), int(indices[-1])
        starts = indices[occupied] - begin
        result[occupied, 0] = np.minimum.reduceat(series.values[begin:end, 0], starts)
        result[occupied, 1] = np.maximum.reduceat(series.values[begin:end, 1], starts)
    return result


def region(config: VisualizerConfig, width: int, height: int) -> Bounds:
    left = min(width - 1, int(round(config.left * width)))
    right = min(width, max(left + 1, int(round((config.left + config.width) * width))))
    top = max(0, min(height - 1, height - int(round((config.bottom + config.height) * height))))
    bottom = min(height, max(top + 1, height - int(round(config.bottom * height))))
    return left, top, right, bottom


def track_regions(width: int, height: int, count: int, config: VisualizerConfig) -> list[Bounds]:
    if config.layout == "overlay":
        return [(0, 0, width, height)] * count
    vertical = config.layout == "stacked"
    length = height if vertical else width
    gap = min(int(round(config.gap * length)), max(0, (length - count) // max(1, count - 1)))
    usable = max(0, length - gap * (count - 1))
    regions = []
    for index in range(count):
        begin = index * usable // count + index * gap
        end = (index + 1) * usable // count + index * gap
        regions.append((0, begin, width, end) if vertical else (begin, 0, end, height))
    return regions


def _blend(image: FloatArray, mask: PixelArray, color: FloatArray, opacity: float) -> None:
    alpha = (mask.astype(np.float32) / np.float32(255) * np.float32(opacity))[..., None]
    image[:] = image * (1 - alpha) + color * alpha


def _waveform(
    image: FloatArray,
    series: FeatureSeries,
    config: VisualizerConfig,
    color: FloatArray,
    timestamp: float,
) -> None:
    height, width = image.shape[:2]
    count = min(config.waveform.points, max(2, width))
    peaks = np.clip(
        waveform_window(series, timestamp, config.waveform.window_seconds, count) * config.gain,
        -1,
        1,
    )
    xs = np.rint(np.linspace(0, width - 1, count)).astype(np.int32)
    upper = np.column_stack([xs, np.rint((1 - peaks[:, 1]) * (height - 1) / 2)]).astype(np.int32)
    lower = np.column_stack([xs, np.rint((1 - peaks[:, 0]) * (height - 1) / 2)]).astype(np.int32)
    mask = np.zeros((height, width), dtype=np.uint8)
    if config.fill_opacity:
        polygon = np.concatenate([upper, lower[::-1]])
        cv2.fillPoly(mask, [polygon], 255, lineType=cv2.LINE_AA)
        _blend(image, mask, color, config.opacity * config.fill_opacity)
        mask.fill(0)
    cv2.polylines(mask, [upper, lower], False, 255, config.line_width, lineType=cv2.LINE_AA)
    _blend(image, mask, color, config.opacity)
    if config.waveform.show_playhead:
        mask.fill(0)
        cv2.line(
            mask,
            ((width - 1) // 2, 0),
            ((width - 1) // 2, height - 1),
            255,
            1,
            lineType=cv2.LINE_AA,
        )
        _blend(image, mask, np.ones(3, dtype=np.float32), config.opacity * 0.35)


def _spectrum(
    image: FloatArray,
    series: FeatureSeries,
    config: VisualizerConfig,
    color: FloatArray,
    timestamp: float,
) -> None:
    height, width = image.shape[:2]
    values = np.clip(spectrum_at(series, timestamp) * config.gain, 0, 1)
    if width < len(values):
        starts = np.linspace(0, len(values), width, endpoint=False, dtype=np.int64)
        values = np.maximum.reduceat(values, starts)
    mask = np.zeros((height, width), dtype=np.uint8)
    count = len(values)
    for index, value in enumerate(values):
        if value <= 1e-6:
            continue
        left = index * width // count
        right = max(left, (index + 1) * width // count - 1)
        bar_width = right - left + 1
        drawing_width = max(1, int(round(bar_width * (1 - config.bar_gap))))
        left += (bar_width - drawing_width) // 2
        right = left + drawing_width - 1
        top = max(0, height - max(1, int(round(float(value) * height))))
        cv2.rectangle(mask, (left, top), (right, height - 1), 255, cv2.FILLED)
    _blend(image, mask, color, config.opacity)


def apply_visualizers(
    image: FloatArray,
    definitions: Mapping[str, VisualizerConfig],
    data: Mapping[str, tuple[FeatureSeries, ...]],
    timestamp: float,
) -> FloatArray:
    """Draw after reactive effects; keep every overlay clipped to its own region."""
    if not definitions:
        return image
    result = image.copy()
    height, width = image.shape[:2]
    for name, config in definitions.items():
        if not config.opacity:
            continue
        left, top, right, bottom = region(config, width, height)
        viewport = result[top:bottom, left:right]
        if config.background_opacity:
            alpha = np.float32(config.opacity * config.background_opacity)
            viewport[:] = viewport * (1 - alpha) + color_rgb(config.background) * alpha
        cells = track_regions(right - left, bottom - top, len(config.tracks), config)
        for track, series, (x0, y0, x1, y1) in zip(config.tracks, data[name], cells, strict=True):
            if x1 <= x0 or y1 <= y0:
                continue
            drawing = _waveform if config.type == "waveform" else _spectrum
            drawing(viewport[y0:y1, x0:x1], series, config, color_rgb(track.color), timestamp)
    return result
