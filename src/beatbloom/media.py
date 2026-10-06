"""FFmpeg discovery, metadata, PCM decoding and subprocess cleanup."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from contextlib import suppress
from fractions import Fraction
from pathlib import Path

import numpy as np

from beatbloom.config import SAMPLE_RATE
from beatbloom.errors import BeatBloomError
from beatbloom.models import AudioTrack, FloatArray, VideoInfo


def require_tools() -> None:
    """Fail early when the external FFmpeg executables are unavailable."""
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        raise BeatBloomError(f"Missing {', '.join(missing)}. Install FFmpeg and add it to PATH.")


def require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise BeatBloomError(f"{label} does not exist or is not a file: {path}")


def run_command(command: list[str]) -> bytes:
    """Run a non-interactive tool and retain its diagnostic output on failure."""
    try:
        result = subprocess.run(command, check=True, capture_output=True)
    except FileNotFoundError as exc:
        raise BeatBloomError(f"Cannot find {command[0]} in PATH") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip()
        raise BeatBloomError(
            f"{command[0]} failed (exit {exc.returncode}): {detail[-4000:]}"
        ) from exc
    return result.stdout


def probe_video(path: Path) -> VideoInfo:
    """Probe the first video stream and preserve fractional frame rates."""
    require_file(path, "Video")
    data = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,avg_frame_rate,r_frame_rate,duration:format=duration",
            "-of",
            "json",
            str(path),
        ]
    )
    try:
        payload = json.loads(data)
        streams = payload["streams"]
        if not streams:
            raise BeatBloomError(f"No video stream found in {path}")
        stream = streams[0]
        fps_text = stream.get("avg_frame_rate", "0/0")
        if fps_text in ("0/0", "0", "N/A"):
            fps_text = stream["r_frame_rate"]
        fps = Fraction(fps_text)
        width, height = int(stream["width"]), int(stream["height"])
        raw_duration = stream.get("duration", payload.get("format", {}).get("duration"))
        duration = float(raw_duration) if raw_duration not in (None, "N/A") else None
        if fps <= 0 or width < 1 or height < 1:
            raise ValueError("non-positive dimensions or frame rate")
        if duration is not None and (not math.isfinite(duration) or duration <= 0):
            duration = None
    except (ValueError, KeyError, IndexError, TypeError, ZeroDivisionError) as exc:
        raise BeatBloomError(f"Invalid video metadata for {path}: {exc}") from exc
    return VideoInfo(width, height, fps, duration)


def load_audio(path: Path) -> AudioTrack:
    """Decode any FFmpeg-supported audio format to mono float32, including Opus."""
    require_file(path, "Audio source")
    data = run_command(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "-f",
            "f32le",
            "-acodec",
            "pcm_f32le",
            "pipe:1",
        ]
    )
    if not data or len(data) % 4:
        raise BeatBloomError(f"No valid audio samples decoded from {path}")
    samples = np.frombuffer(data, dtype="<f4").astype(np.float32)
    if not np.all(np.isfinite(samples)):
        raise BeatBloomError(f"Audio contains non-finite samples: {path}")
    return AudioTrack(samples, SAMPLE_RATE)


def load_stereo(path: Path) -> FloatArray:
    """Decode stereo explicitly for Demucs without depending on its audio codecs."""
    require_file(path, "Audio source")
    data = run_command(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "2",
            "-ar",
            str(SAMPLE_RATE),
            "-f",
            "f32le",
            "pipe:1",
        ]
    )
    if not data or len(data) % 8:
        raise BeatBloomError(f"No valid stereo audio decoded from {path}")
    samples = np.frombuffer(data, dtype="<f4").reshape(-1, 2).T.copy()
    if not np.all(np.isfinite(samples)):
        raise BeatBloomError(f"Audio contains non-finite samples: {path}")
    return np.asarray(samples, dtype=np.float32)


def audio_duration(path: Path) -> float:
    """Probe the original mix on warm runs instead of decoding it in full again."""
    require_file(path, "Audio")
    payload = json.loads(
        run_command(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=duration:format=duration",
                "-of",
                "json",
                str(path),
            ]
        )
    )
    streams = payload.get("streams", [])
    if not streams:
        raise BeatBloomError(f"No audio stream found in {path}")
    raw = streams[0].get("duration", payload.get("format", {}).get("duration"))
    try:
        duration = float(raw)
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("non-positive audio duration")
        return duration
    except (TypeError, ValueError):
        return load_audio(path).duration


def stop_process(process: subprocess.Popen[bytes] | None) -> None:
    """Terminate and reap a child after failure or interruption."""
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    for stream in (process.stdin, process.stdout):
        if stream is not None and not stream.closed:
            with suppress(BrokenPipeError, OSError):
                stream.close()
