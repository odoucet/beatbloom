"""Play rendered previews with ffplay and reap the player on interruption."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from beatbloom.errors import BeatBloomError
from beatbloom.media import stop_process


def require_player() -> None:
    if shutil.which("ffplay") is None:
        raise BeatBloomError(
            "Missing ffplay. Install FFmpeg or save a preview with --no-play --output preview.mp4."
        )


def play_preview(path: Path) -> None:
    """Wait until the player closes; no shell is involved in opening the file."""
    require_player()
    player: subprocess.Popen[bytes] | None = None
    with tempfile.TemporaryFile() as diagnostics:
        try:
            player = subprocess.Popen(
                ["ffplay", "-hide_banner", "-loglevel", "error", "-autoexit", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=diagnostics,
            )
            status = player.wait()
            if status:
                diagnostics.seek(0)
                detail = diagnostics.read().decode("utf-8", errors="replace").strip()[-4000:]
                raise BeatBloomError(f"ffplay failed (exit {status}): {detail}")
        finally:
            stop_process(player)
