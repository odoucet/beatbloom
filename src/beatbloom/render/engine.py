"""Analyze complete tracks, stream RGB frames and atomically commit encoded output."""

from __future__ import annotations

import logging
import math
import os
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import IO

import numpy as np

from beatbloom.analysis.pipeline import analyze
from beatbloom.config import ProjectConfig, load_config
from beatbloom.errors import BeatBloomError
from beatbloom.media import (
    audio_duration,
    load_audio,
    probe_video,
    require_file,
    require_tools,
    stop_process,
)
from beatbloom.models import RenderOptions, RenderResult, Signal, VideoInfo
from beatbloom.render.effects import apply_effects, parameters_at

LOGGER = logging.getLogger(__name__)
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv"}


def _validate_options(options: RenderOptions, config: ProjectConfig) -> None:
    if not math.isfinite(options.start) or options.start < 0:
        raise BeatBloomError("Start must be a finite number >= 0")
    if options.duration is not None and (
        not math.isfinite(options.duration) or options.duration <= 0
    ):
        raise BeatBloomError("Duration must be a finite number > 0")
    if not 0 <= options.crf <= 51:
        raise BeatBloomError("CRF must be between 0 and 51")
    if options.fps is not None and options.fps <= 0:
        raise BeatBloomError("Frame rate must be positive")
    if options.size is not None and any(value < 2 or value % 2 for value in options.size):
        raise BeatBloomError("Output dimensions must be even numbers >= 2")
    if options.output.suffix.lower() not in VIDEO_SUFFIXES:
        raise BeatBloomError("Output must have an .mp4, .mov or .mkv extension")
    inputs = {options.video.resolve(), options.audio.resolve()}
    for path in (options.drive, options.config):
        if path is not None:
            inputs.add(path.resolve())
    inputs.update(
        Path(signal.source).resolve()
        for signal in config.signals.values()
        if signal.source is not None
    )
    for path in inputs:
        require_file(path, "Input")
    outputs = [options.output]
    if options.plot is not None:
        if options.plot.suffix.lower() not in {".png", ".pdf", ".svg"}:
            raise BeatBloomError("Plot must have a .png, .pdf or .svg extension")
        outputs.append(options.plot)
    if len({path.resolve() for path in outputs}) != len(outputs):
        raise BeatBloomError("Video and plot outputs must use different paths")
    for path in outputs:
        if path.resolve() in inputs:
            raise BeatBloomError(f"Output must not replace an input: {path}")
        if path.exists() and (not options.overwrite or not path.is_file()):
            raise BeatBloomError(
                f"Output already exists: {path}. Use --overwrite to replace a file."
            )
        path.parent.mkdir(parents=True, exist_ok=True)


def _render_duration(
    options: RenderOptions, video: VideoInfo, audio_duration: float, *, warn: bool = True
) -> float:
    available_end = min(audio_duration, video.duration) if video.duration else audio_duration
    available = available_end - options.start
    if available <= 0:
        raise BeatBloomError(
            f"Start {options.start:g} s is outside the available audio/video ({available_end:g} s)"
        )
    if warn and options.duration is not None and options.duration > available:
        LOGGER.warning("Requested excerpt exceeds input duration; rendering %.3f s", available)
    return min(options.duration, available) if options.duration is not None else available


def _read_frame(stream: IO[bytes], size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    data = b"".join(chunks)
    if data and remaining:
        raise BeatBloomError(f"Decoder returned an incomplete frame ({len(data)}/{size} bytes)")
    return data


def _diagnostics(stream: IO[bytes]) -> str:
    stream.seek(0)
    return stream.read().decode("utf-8", errors="replace").strip()[-4000:]


def _encode(
    options: RenderOptions,
    config: ProjectConfig,
    signals: dict[str, Signal],
    video: VideoInfo,
    duration: float,
    temporary: Path,
) -> int:
    width, height = options.size or (video.width, video.height)
    if width % 2 or height % 2:
        raise BeatBloomError("Input dimensions are odd; choose even output dimensions with --size")
    fps = str(video.fps)
    frame_count = math.ceil(duration * float(video.fps) - 1e-9)
    # A seek between source frames can leave a positive first PTS. Pad that
    # gap so the raw stream starts at zero, as the encoder and audio expect.
    filters = [f"fps={fps}:start_time=0"]
    if options.size is not None:
        filters.extend(
            [
                f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos",
                f"crop={width}:{height}",
            ]
        )
    decode = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-noautorotate",
        "-ss",
        str(options.start),
        "-i",
        str(options.video),
        "-t",
        str(duration),
        "-map",
        "0:v:0",
        "-an",
        "-sn",
        "-dn",
        "-vf",
        ",".join(filters),
        "-frames:v",
        str(frame_count),
        "-threads",
        "1",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "pipe:1",
    ]
    encode = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{width}x{height}",
        "-r",
        fps,
        "-i",
        "pipe:0",
        "-ss",
        str(options.start),
        "-t",
        str(duration),
        "-i",
        str(options.audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-map_metadata",
        "-1",
    ]
    if options.grade:
        encode.extend(["-vf", options.grade])
    encode.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            options.preset,
            "-crf",
            str(options.crf),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "320k",
            "-shortest",
        ]
    )
    if options.output.suffix.lower() in {".mp4", ".mov"}:
        encode.extend(["-movflags", "+faststart"])
    encode.append(str(temporary))
    reader: subprocess.Popen[bytes] | None = None
    writer: subprocess.Popen[bytes] | None = None
    frames = 0
    # File-backed stderr cannot fill a pipe and deadlock either FFmpeg process.
    with tempfile.TemporaryFile() as decoder_log, tempfile.TemporaryFile() as encoder_log:
        try:
            LOGGER.debug("Decoder arguments: %s", decode)
            LOGGER.debug("Encoder arguments: %s", encode)
            reader = subprocess.Popen(decode, stdout=subprocess.PIPE, stderr=decoder_log)
            writer = subprocess.Popen(encode, stdin=subprocess.PIPE, stderr=encoder_log)
            assert reader.stdout is not None and writer.stdin is not None
            frame_size = width * height * 3
            while frames < frame_count:
                raw = _read_frame(reader.stdout, frame_size)
                if not raw:
                    break
                image = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)
                normalized = np.asarray(image, dtype=np.float32) / np.float32(255)
                timestamp = options.start + frames / float(video.fps)
                result = apply_effects(normalized, parameters_at(config, signals, timestamp))
                writer.stdin.write((result * 255 + 0.5).astype(np.uint8).tobytes())
                frames += 1
                if frames % 240 == 0:
                    LOGGER.info("Rendered %s/%s frames", frames, frame_count)
            reader.stdout.close()
            decoder_status = reader.wait()
            writer.stdin.close()
            encoder_status = writer.wait()
            if decoder_status != 0:
                raise BeatBloomError(
                    f"FFmpeg decoder failed (exit {decoder_status}): {_diagnostics(decoder_log)}"
                )
            if encoder_status != 0:
                raise BeatBloomError(
                    f"FFmpeg encoder failed (exit {encoder_status}): {_diagnostics(encoder_log)}"
                )
            if frames == 0:
                raise BeatBloomError("No video frames decoded for the requested excerpt")
            if frames < frame_count:
                LOGGER.warning("Video ended after %s/%s requested frames", frames, frame_count)
        except BrokenPipeError as exc:
            stop_process(reader)
            stop_process(writer)
            detail = _diagnostics(encoder_log) or _diagnostics(decoder_log)
            raise BeatBloomError(f"FFmpeg stopped accepting frames: {detail}") from exc
        finally:
            stop_process(reader)
            stop_process(writer)
    return frames


def render_video(options: RenderOptions, config: ProjectConfig | None = None) -> RenderResult:
    """Render an excerpt using full-track normalization and the original audio mix."""
    require_tools()
    config = config if config is not None else load_config(options.config)
    _validate_options(options, config)
    video = probe_video(options.video)
    if options.fps is not None:
        video = replace(video, fps=options.fps)
    _render_duration(options, video, audio_duration(options.audio), warn=False)
    analysis = analyze(
        options.audio,
        config,
        drive=options.drive,
        cache_dir=options.cache_dir,
        refresh=options.refresh,
    )
    signals = analysis.signals
    duration = _render_duration(options, video, analysis.audio_duration)
    width, height = options.size or (video.width, video.height)
    LOGGER.info(
        "%sx%s @ %s fps; render %.3f -> %.3f s",
        width,
        height,
        video.fps,
        options.start,
        options.start + duration,
    )
    if options.plot is not None:
        from beatbloom.plot import save_plot

        drive = load_audio(options.drive or options.audio)
        save_plot(options.plot, drive, config, signals, options.start, duration, options.overwrite)
    descriptor, filename = tempfile.mkstemp(
        prefix=f".{options.output.stem}-", suffix=options.output.suffix, dir=options.output.parent
    )
    os.close(descriptor)
    temporary = Path(filename)
    try:
        frames = _encode(options, config, signals, video, duration, temporary)
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise BeatBloomError("Encoder produced an empty output file")
        if options.output.exists() and not options.overwrite:
            raise BeatBloomError(f"Output appeared during rendering: {options.output}")
        os.replace(temporary, options.output)
        return RenderResult(options.output, frames, video.fps)
    finally:
        temporary.unlink(missing_ok=True)
