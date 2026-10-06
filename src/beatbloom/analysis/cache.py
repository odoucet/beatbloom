"""Validated, versioned NPZ caches for raw features and normalized envelopes."""

from __future__ import annotations

import json
import logging
import math
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from zipfile import BadZipFile

import numpy as np

from beatbloom.cache import CacheStore, file_hash, publish_directory, write_json
from beatbloom.models import FeatureSeries

LOGGER = logging.getLogger(__name__)
CACHE_FORMAT = 1


def validate_series(
    series: FeatureSeries,
    normalized: bool = False,
    *,
    columns: int | None = None,
    signed: bool = False,
    extrema: bool = False,
) -> None:
    times, values = series.timestamps, series.values
    if (
        times.ndim != 1
        or values.ndim != (1 if columns is None else 2)
        or len(times) != len(values)
        or not len(values)
        or times.dtype != np.float64
        or values.dtype != np.float32
        or not np.all(np.isfinite(times))
        or not np.all(np.isfinite(values))
        or not math.isfinite(series.duration)
        or series.duration <= 0
        or times[0] != 0
        or np.any(np.diff(times) <= 0)
        or times[-1] > series.duration + 1e-8
        or (not signed and np.any(values < 0))
        or (normalized and signed and np.any(values < -1))
        or (normalized and np.any(values > 1))
    ):
        raise ValueError("invalid timestamped cache series")
    if columns is not None and values.shape[1] != columns:
        raise ValueError("invalid cache column count")
    if extrema and (columns != 2 or np.any(values[:, 0] > values[:, 1])):
        raise ValueError("invalid waveform extrema")


class AnalysisCache:
    def __init__(self, store: CacheStore) -> None:
        self.store = store

    def get(
        self,
        namespace: str,
        key: str,
        parameters: Mapping[str, object],
        compute: Callable[[], FeatureSeries],
        *,
        refresh: bool = False,
        columns: int | None = None,
        signed: bool = False,
        extrema: bool = False,
    ) -> tuple[FeatureSeries, bool]:
        destination = self.store.entry(namespace, key)
        normalized = namespace in {"signals", "visualizers"}
        with self.store.locked(namespace, key):
            if destination.exists() and not refresh:
                try:
                    manifest = json.loads((destination / "manifest.json").read_text())
                    payload = destination / "series.npz"
                    if (
                        manifest["cache_format"] != CACHE_FORMAT
                        or manifest["key"] != key
                        or manifest["namespace"] != namespace
                        or manifest["parameters"] != parameters
                        or manifest["sha256"] != file_hash(payload)
                    ):
                        raise ValueError("cache manifest does not match")
                    with np.load(payload, allow_pickle=False) as data:
                        if data["duration"].shape != ():
                            raise ValueError("cached duration must be a scalar")
                        series = FeatureSeries(
                            data["timestamps"], data["values"], float(data["duration"])
                        )
                    validate_series(
                        series, normalized, columns=columns, signed=signed, extrema=extrema
                    )
                    LOGGER.info("Cache hit: %s/%s", namespace, key[:12])
                    return series, True
                except (OSError, ValueError, KeyError, TypeError, EOFError, BadZipFile) as exc:
                    LOGGER.warning("Rebuilding invalid %s cache %s: %s", namespace, key[:12], exc)
            series = compute()
            validate_series(series, normalized, columns=columns, signed=signed, extrema=extrema)
            with tempfile.TemporaryDirectory(prefix=f".{key}-", dir=destination.parent) as name:
                staged = Path(name)
                payload = staged / "series.npz"
                np.savez_compressed(
                    payload,
                    timestamps=series.timestamps,
                    values=series.values,
                    duration=np.float64(series.duration),
                )
                write_json(
                    staged / "manifest.json",
                    {
                        "cache_format": CACHE_FORMAT,
                        "namespace": namespace,
                        "key": key,
                        "parameters": dict(parameters),
                        "sha256": file_hash(payload),
                    },
                )
                publish_directory(staged, destination)
            return series, False
