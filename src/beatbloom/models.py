"""Typed data exchanged between analysis and rendering."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import TypeAlias

import numpy as np
from numpy.typing import NDArray

FloatArray: TypeAlias = NDArray[np.float32]
PixelArray: TypeAlias = NDArray[np.uint8]


@dataclass(frozen=True)
class AudioTrack:
    """Mono PCM at the analysis sample rate."""

    samples: FloatArray
    sample_rate: int

    @property
    def duration(self) -> float:
        return len(self.samples) / self.sample_rate


@dataclass(frozen=True)
class VideoInfo:
    """Video metadata and the constant frame rate used for rendering."""

    width: int
    height: int
    fps: Fraction
    duration: float | None


@dataclass(frozen=True)
class Signal:
    """A normalized envelope indexed by absolute audio time."""

    name: str
    values: FloatArray
    fps: float
    duration: float

    def at(self, timestamp: float) -> float:
        """Interpolate within the track; a finished or not-yet-started track is silent."""
        if timestamp < 0 or timestamp >= self.duration or len(self.values) == 0:
            return 0.0
        position = timestamp * self.fps
        left = min(int(position), len(self.values) - 1)
        right = min(left + 1, len(self.values) - 1)
        fraction = position - left
        return float(self.values[left] * (1 - fraction) + self.values[right] * fraction)


@dataclass(frozen=True)
class EffectParameters:
    """Resolved per-frame intensities; brightness is multiplicative."""

    bloom: float = 0.0
    exposure: float = 0.0
    saturation: float = 0.0
    zoom: float = 0.0
    brightness: float = 1.0


@dataclass(frozen=True)
class RenderOptions:
    """Validated CLI options passed to the rendering pipeline."""

    video: Path
    audio: Path
    output: Path
    drive: Path | None = None
    config: Path | None = None
    start: float = 0.0
    duration: float | None = None
    size: tuple[int, int] | None = None
    crf: int = 16
    preset: str = "slow"
    grade: str | None = None
    plot: Path | None = None
    overwrite: bool = False


@dataclass(frozen=True)
class RenderResult:
    """The successfully committed output and its frame count."""

    output: Path
    frames: int
    fps: Fraction

    @property
    def duration(self) -> float:
        return self.frames / float(self.fps)
