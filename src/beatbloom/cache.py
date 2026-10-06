"""Content addressing, cross-process locks and atomic cache publication."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock, Timeout
from platformdirs import user_cache_path

from beatbloom.errors import BeatBloomError


def fingerprint(parameters: Mapping[str, object]) -> str:
    encoded = json.dumps(parameters, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    """Write an individual manifest without exposing a truncated JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def publish_directory(staged: Path, destination: Path) -> None:
    """Replace an entry under its cache lock; failed producers retain the old entry."""
    backup = destination.with_name(f".{destination.name}-old-{uuid.uuid4().hex}")
    moved = False
    try:
        if destination.exists():
            destination.replace(backup)
            moved = True
        staged.replace(destination)
    except BaseException:
        if moved and not destination.exists():
            backup.replace(destination)
        raise
    finally:
        if backup.is_dir():
            shutil.rmtree(backup)
        elif backup.exists():
            backup.unlink()


class CacheStore:
    """One user cache root shared by separation, features, envelopes and manifests."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (
            root if root is not None else user_cache_path("beatbloom", appauthor=False)
        ).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def entry(self, namespace: str, key: str) -> Path:
        directory = self.root / namespace
        directory.mkdir(parents=True, exist_ok=True)
        return directory / key

    @contextmanager
    def locked(self, namespace: str, key: str) -> Iterator[None]:
        directory = self.root / "locks"
        directory.mkdir(exist_ok=True)
        try:
            with FileLock(directory / f"{namespace}-{key}.lock", timeout=600):
                yield
        except Timeout as exc:
            raise BeatBloomError(
                f"Cache entry is busy: {namespace}/{key}; retry when it finishes"
            ) from exc
