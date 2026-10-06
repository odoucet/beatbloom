"""Backend interface and cached separation results."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from beatbloom.config import SeparationConfig


class SeparationBackend(Protocol):
    def versions(self) -> dict[str, str]:
        """Return versions without importing or loading neural models."""
        ...

    def separate(self, audio: Path, destination: Path, config: SeparationConfig) -> dict[str, Path]:
        """Write aligned float32 WAV stems into destination."""
        ...


@dataclass(frozen=True)
class StemSet:
    stems: dict[str, Path]
    hashes: dict[str, str]
    manifest: Path
    key: str
    cached: bool
