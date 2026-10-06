from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest

from beatbloom.analysis.cache import AnalysisCache
from beatbloom.cache import CacheStore, file_hash, fingerprint
from beatbloom.models import FeatureSeries


def series() -> FeatureSeries:
    return FeatureSeries(
        np.array([0, 0.5], dtype=np.float64), np.array([0.2, 0.8], dtype=np.float32), 1.0
    )


def test_content_hash_and_canonical_parameters(tmp_path: Path) -> None:
    one, two = tmp_path / "one.wav", tmp_path / "renamed.wav"
    one.write_bytes(b"same content")
    two.write_bytes(one.read_bytes())
    assert file_hash(one) == file_hash(two)
    two.write_bytes(b"new content!")
    assert file_hash(one) != file_hash(two)
    assert fingerprint({"b": 2, "a": 1}) == fingerprint({"a": 1, "b": 2})


def test_cache_is_safe_to_read_and_reuses_without_computing(tmp_path: Path) -> None:
    cache = AnalysisCache(CacheStore(tmp_path))
    expected, hit = cache.get("signals", "key", {"feature": "rms"}, series)
    assert not hit

    def unexpected() -> FeatureSeries:
        pytest.fail("warm cache must not recompute")

    reused, hit = cache.get("signals", "key", {"feature": "rms"}, unexpected)
    assert hit
    np.testing.assert_array_equal(reused.values, expected.values)
    np.testing.assert_array_equal(reused.timestamps, expected.timestamps)
    with np.load(tmp_path / "signals/key/series.npz", allow_pickle=False) as payload:
        assert payload["values"].dtype == np.float32
        assert payload["timestamps"].dtype == np.float64


@pytest.mark.parametrize(
    "corruption",
    ["manifest", "payload", "hash", "timestamps", "nan", "object", "duration", "range"],
)
def test_corrupt_or_invalid_cache_is_rebuilt(tmp_path: Path, corruption: str) -> None:
    store = CacheStore(tmp_path)
    cache = AnalysisCache(store)
    cache.get("signals", "key", {}, series)
    entry = store.entry("signals", "key")
    payload, manifest_path = entry / "series.npz", entry / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if corruption == "manifest":
        manifest_path.write_text("{broken")
    elif corruption == "payload":
        payload.write_bytes(b"not an NPZ file")
    elif corruption == "hash":
        manifest["sha256"] = "incorrect"
        manifest_path.write_text(json.dumps(manifest))
    else:
        times, values, duration = series().timestamps, series().values, np.float64(1)
        if corruption == "timestamps":
            times = np.array([0, 0], dtype=np.float64)
        elif corruption == "nan":
            values = np.array([0, np.nan], dtype=np.float32)
        elif corruption == "object":
            values = np.array(["untrusted", "data"], dtype=object)
        elif corruption == "duration":
            duration = np.array([1], dtype=np.float64)
        elif corruption == "range":
            values = np.array([0, 1.2], dtype=np.float32)
        np.savez(payload, timestamps=times, values=values, duration=duration)
        manifest["sha256"] = file_hash(payload)
        manifest_path.write_text(json.dumps(manifest))
    result, hit = cache.get("signals", "key", {}, series)
    assert not hit
    np.testing.assert_array_equal(result.values, series().values)
    assert cache.get("signals", "key", {}, series)[1]


def test_failed_refresh_preserves_good_entry(tmp_path: Path) -> None:
    store = CacheStore(tmp_path)
    cache = AnalysisCache(store)
    cache.get("signals", "key", {}, series)
    before = file_hash(store.entry("signals", "key") / "series.npz")

    def failing() -> FeatureSeries:
        raise RuntimeError("producer failed")

    with pytest.raises(RuntimeError, match="producer failed"):
        cache.get("signals", "key", {}, failing, refresh=True)
    assert file_hash(store.entry("signals", "key") / "series.npz") == before
    assert cache.get("signals", "key", {}, series)[1]
    assert not list((tmp_path / "signals").glob(".*"))


def test_concurrent_requests_compute_once(tmp_path: Path) -> None:
    cache = AnalysisCache(CacheStore(tmp_path))
    barrier = threading.Barrier(2)
    calls = 0

    def compute() -> FeatureSeries:
        nonlocal calls
        calls += 1
        return series()

    def request() -> bool:
        barrier.wait(timeout=5)
        return cache.get("signals", "shared", {}, compute)[1]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: request(), range(2)))
    assert sorted(results) == [False, True]
    assert calls == 1


@pytest.mark.parametrize("corruption", ["columns", "range", "extrema"])
def test_invalid_waveform_matrix_cache_is_rebuilt(tmp_path: Path, corruption: str) -> None:
    cache = AnalysisCache(CacheStore(tmp_path))
    good = FeatureSeries(
        np.array([0, 0.5], dtype=np.float64),
        np.array([[-0.5, 0.8], [-0.2, 0.6]], dtype=np.float32),
        1.0,
    )
    kwargs = {"columns": 2, "signed": True, "extrema": True}
    cache.get("visualizers", "waveform", {}, lambda: good, **kwargs)
    entry = tmp_path / "visualizers/waveform"
    values = good.values.copy()
    if corruption == "columns":
        values = np.ones((2, 3), dtype=np.float32)
    elif corruption == "range":
        values[0, 0] = -1.5
    else:
        values[0] = 0.9, -0.8
    payload = entry / "series.npz"
    np.savez(payload, timestamps=good.timestamps, values=values, duration=np.float64(1))
    manifest_path = entry / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["sha256"] = file_hash(payload)
    manifest_path.write_text(json.dumps(manifest))
    recovered, hit = cache.get("visualizers", "waveform", {}, lambda: good, **kwargs)
    assert not hit
    np.testing.assert_array_equal(recovered.values, good.values)
