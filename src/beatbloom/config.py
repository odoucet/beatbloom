"""Schema v2: named audio signals, independent effect mappings and separation settings."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from beatbloom.errors import BeatBloomError

SAMPLE_RATE = 44_100
NYQUIST = SAMPLE_RATE / 2
FeatureName = Literal["onset", "rms", "loudness"]
StemName = Literal["mix", "drums", "bass", "vocals", "other", "guitar", "piano"]
EffectName = Literal["bloom", "exposure", "saturation", "zoom", "brightness"]
NonNegative = Annotated[float, Field(ge=0)]
Percentile = Annotated[float, Field(gt=0, le=100)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


class SeparationConfig(StrictModel):
    """Options that affect the identity of cached Demucs output."""

    backend: Literal["demucs"] = "demucs"
    model: Literal["htdemucs_6s", "htdemucs"] = "htdemucs_6s"
    device: str = Field(default="auto", pattern=r"^(auto|cpu|mps|cuda(:[0-9]+)?)$")
    shifts: Annotated[int, Field(ge=0)] = 1
    overlap: Annotated[float, Field(ge=0, lt=1)] = 0.25
    segment: Annotated[int, Field(gt=0, le=7)] | None = None
    jobs: Annotated[int, Field(ge=0)] = 0
    seed: Annotated[int, Field(ge=0, le=2**32 - 1)] = 0

    @property
    def stems(self) -> tuple[str, ...]:
        basic = ("drums", "bass", "vocals", "other")
        return (*basic, "guitar", "piano") if self.model == "htdemucs_6s" else basic


class SignalConfig(StrictModel):
    """One source and its analysis/envelope parameters, independent of video FPS."""

    stem: StemName | None = None
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

    @field_validator("source")
    @classmethod
    def nonblank_source(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("source must not be blank")
        return value

    @property
    def reference(self) -> float:
        if self.ref_percentile is not None:
            return self.ref_percentile
        return 99.0 if self.feature == "loudness" else 99.5

    @model_validator(mode="after")
    def validate_signal(self) -> SignalConfig:
        if self.source is not None and self.stem is not None:
            raise ValueError("choose either source or stem, not both")
        if (self.low or 0) >= (self.high if self.high is not None else NYQUIST):
            raise ValueError("low must be strictly less than high")
        if self.feature == "loudness" and self.floor_percentile >= self.reference:
            raise ValueError("floor_percentile must be less than ref_percentile for loudness")
        return self


class EffectConfig(StrictModel):
    """Map a named signal to an additive effect or a multiplicative brightness range."""

    signal: str = Field(min_length=1)
    effect: EffectName
    amount: NonNegative | None = None
    range: tuple[NonNegative, NonNegative] | None = None

    @model_validator(mode="after")
    def validate_mapping(self) -> EffectConfig:
        if self.effect == "brightness":
            if self.range is None or self.amount is not None:
                raise ValueError("brightness requires range: [dark, bright] and no amount")
        elif self.amount is None or self.range is not None:
            raise ValueError("additive effects require amount and no range")
        return self


class ProjectConfig(StrictModel):
    """Only schema v2 is accepted; legacy bands JSON has been removed."""

    schema_version: Literal[2]
    signals: dict[str, SignalConfig] = Field(min_length=1)
    effects: tuple[EffectConfig, ...] = ()
    separation: SeparationConfig = Field(default_factory=SeparationConfig)

    @model_validator(mode="after")
    def validate_references(self) -> ProjectConfig:
        for name, signal in self.signals.items():
            if not name.strip():
                raise ValueError("signal names must not be blank")
            if signal.stem not in (None, "mix") and signal.stem not in self.separation.stems:
                raise ValueError(
                    f"stem {signal.stem!r} is unavailable with {self.separation.model}"
                )
        for mapping in self.effects:
            if mapping.signal not in self.signals:
                raise ValueError(f"effect references undefined signal {mapping.signal!r}")
        return self


def default_config() -> ProjectConfig:
    return ProjectConfig(
        schema_version=2,
        signals={
            "volume_global": SignalConfig(
                feature="loudness",
                attack_ms=400.0,
                release_ms=2000.0,
            ),
            "piano_attaques": SignalConfig(
                low=400.0,
                high=2000.0,
                attack_ms=10.0,
                release_ms=250.0,
                gate=0.35,
                gamma=2.0,
            ),
        },
        effects=(
            EffectConfig(signal="volume_global", effect="brightness", range=(0.6, 1.05)),
            EffectConfig(signal="piano_attaques", effect="bloom", amount=1.2),
            EffectConfig(signal="piano_attaques", effect="exposure", amount=0.10),
            EffectConfig(signal="piano_attaques", effect="saturation", amount=0.15),
        ),
    )


def load_config(path: Path | None = None) -> ProjectConfig:
    """Load v2 JSON; resolve source paths relative to the configuration file."""
    if path is None:
        return default_config()
    try:
        config = ProjectConfig.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BeatBloomError(f"Cannot read configuration {path}: {exc}") from exc
    except (ValidationError, UnicodeError) as exc:
        raise BeatBloomError(
            f"Invalid configuration {path}: "
            "schema_version: 2 with signals and effects is required.\n"
            f"Legacy bands JSON is not supported.\n{exc}"
        ) from exc
    base = path.resolve().parent
    signals = {
        name: signal.model_copy(update={"source": str((base / signal.source).resolve())})
        if signal.source is not None
        else signal
        for name, signal in config.signals.items()
    }
    return config.model_copy(update={"signals": signals})
