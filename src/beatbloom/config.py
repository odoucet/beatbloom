"""Validated v1 configuration, compatible with the original bands.json."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from beatbloom.errors import BeatBloomError

SAMPLE_RATE = 44_100
NYQUIST = SAMPLE_RATE / 2
EffectName = Literal["bloom", "exposure", "saturation", "zoom"]
FeatureName = Literal["onset", "rms", "loudness"]
NonNegative = Annotated[float, Field(ge=0)]
Percentile = Annotated[float, Field(gt=0, le=100)]
LOGGER = logging.getLogger(__name__)


class StrictModel(BaseModel):
    """Reject misspelled keys, stringified numbers and non-finite values."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


class BandConfig(StrictModel):
    """One audio feature and its visual mappings."""

    name: str = Field(min_length=1)
    source: str | None = Field(default=None, min_length=1)
    low: Annotated[float, Field(ge=0, lt=NYQUIST)] | None = None
    high: Annotated[float, Field(gt=0, le=NYQUIST)] | None = None
    feature: FeatureName = "onset"
    attack_ms: NonNegative = 10.0
    release_ms: NonNegative = 400.0
    gate: Annotated[float, Field(ge=0, lt=1)] = 0.0
    gamma: Annotated[float, Field(gt=0)] = 1.0
    ref_percentile: Percentile | None = None
    floor_percentile: Annotated[float, Field(ge=0, lt=100)] = 5.0
    effects: dict[EffectName, NonNegative] = Field(default_factory=dict)
    brightness: tuple[NonNegative, NonNegative] | None = None

    @field_validator("name", "source")
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        """A whitespace-only label or filename is usually a mistake."""
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value

    @property
    def reference(self) -> float:
        """Retain the feature-specific percentile defaults of the prototype."""
        if self.ref_percentile is not None:
            return self.ref_percentile
        return 99.0 if self.feature == "loudness" else 99.5

    @model_validator(mode="after")
    def validate_ranges(self) -> BandConfig:
        """Validate relationships that individual field bounds cannot express."""
        if (self.low or 0) >= (self.high if self.high is not None else NYQUIST):
            raise ValueError("low must be strictly less than high")
        if self.feature == "loudness" and self.floor_percentile >= self.reference:
            raise ValueError("floor_percentile must be less than ref_percentile for loudness")
        return self


class ProjectConfig(StrictModel):
    """The public JSON configuration format for BeatBloom 0.1."""

    schema_version: Literal[1] = 1
    bands: tuple[BandConfig, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_names(self) -> ProjectConfig:
        names = [band.name for band in self.bands]
        if len(names) != len(set(names)):
            raise ValueError("band names must be unique")
        return self


def default_config() -> ProjectConfig:
    """Default to global brightness and piano-range attacks on the mix."""
    return ProjectConfig(
        bands=(
            BandConfig(
                name="volume_global",
                feature="loudness",
                attack_ms=400.0,
                release_ms=2000.0,
                brightness=(0.6, 1.05),
            ),
            BandConfig(
                name="piano_attaques",
                low=400.0,
                high=2000.0,
                attack_ms=10.0,
                release_ms=250.0,
                gate=0.35,
                gamma=2.0,
                effects={"bloom": 1.2, "exposure": 0.10, "saturation": 0.15},
            ),
        )
    )


def load_config(path: Path | None = None) -> ProjectConfig:
    """Load JSON and resolve source paths relative to the configuration file."""
    if path is None:
        return default_config()
    try:
        config = ProjectConfig.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BeatBloomError(f"Cannot read configuration {path}: {exc}") from exc
    except (ValidationError, UnicodeError) as exc:
        raise BeatBloomError(f"Invalid configuration {path}:\n{exc}") from exc
    base = path.resolve().parent
    bands = tuple(
        band.model_copy(update={"source": str((base / band.source).resolve())})
        if band.source is not None
        else band
        for band in config.bands
    )
    LOGGER.debug("Loaded %s bands from %s", len(bands), path)
    return config.model_copy(update={"bands": bands})
