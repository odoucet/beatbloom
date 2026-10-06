from __future__ import annotations

import json
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from beatbloom.cli import main
from beatbloom.errors import BeatBloomError
from beatbloom.media import probe_video
from beatbloom.models import RenderOptions
from beatbloom.render.engine import render_video

pytestmark = pytest.mark.integration


def write_config(root: Path, *, source: str | None = None) -> Path:
    band: dict[str, object] = {
        "name": "energy",
        "feature": "rms",
        "attack_ms": 0,
        "release_ms": 0,
        "effects": {"exposure": 0.5},
    }
    if source is not None:
        band["source"] = source
    path = root / "bands.json"
    path.write_text(json.dumps({"bands": [band]}))
    return path


def video_pixels(path: Path) -> np.ndarray:
    result = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    )
    return np.frombuffer(result.stdout, dtype=np.uint8)


def test_real_render_with_audio_effects_resize_and_excerpt(
    media_files: tuple[Path, Path], tmp_path: Path
) -> None:
    video, audio = media_files
    output = tmp_path / "render with spaces.mp4"
    result = render_video(
        RenderOptions(
            video,
            audio,
            output,
            config=write_config(tmp_path),
            start=0.5,
            duration=0.75,
            size=(80, 60),
            preset="ultrafast",
            crf=18,
        )
    )
    info = probe_video(output)
    assert result.frames == 9
    assert (info.width, info.height) == (80, 60)
    assert info.fps == Fraction(12, 1)
    assert info.duration == pytest.approx(0.75, abs=1 / 12)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    streams = json.loads(probe.stdout)["streams"]
    assert {stream["codec_type"] for stream in streams} == {"video", "audio"}
    assert video_pixels(output).mean() > video_pixels(video).mean() * 1.25


def test_per_band_source_and_original_audio_mux(
    media_files: tuple[Path, Path], tmp_path: Path
) -> None:
    video, audio = media_files
    silent = tmp_path / "silent.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            "2",
            str(silent),
        ],
        check=True,
        capture_output=True,
    )
    output = tmp_path / "silent-driver.mp4"
    render_video(
        RenderOptions(
            video,
            audio,
            output,
            config=write_config(tmp_path, source="silent.wav"),
            duration=0.5,
            preset="ultrafast",
        )
    )
    assert video_pixels(output).mean() == pytest.approx(video_pixels(video).mean(), abs=2)
    decoded = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(output),
            "-map",
            "0:a:0",
            "-f",
            "f32le",
            "-ac",
            "1",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    )
    assert np.max(np.abs(np.frombuffer(decoded.stdout, dtype="<f4"))) > 0.05


def test_invalid_grade_preserves_existing_output_and_cleans_temporary_files(
    media_files: tuple[Path, Path], tmp_path: Path
) -> None:
    video, audio = media_files
    output = tmp_path / "existing.mp4"
    output.write_bytes(b"previous successful output")
    with pytest.raises(BeatBloomError, match="FFmpeg"):
        render_video(
            RenderOptions(
                video,
                audio,
                output,
                config=write_config(tmp_path),
                duration=0.5,
                grade="filter_that_does_not_exist",
                preset="ultrafast",
                overwrite=True,
            )
        )
    assert output.read_bytes() == b"previous successful output"
    assert not list(tmp_path.glob(".existing-*.mp4"))


def test_output_cannot_replace_input(media_files: tuple[Path, Path]) -> None:
    video, audio = media_files
    with pytest.raises(BeatBloomError, match="must not replace an input"):
        render_video(RenderOptions(video, audio, video, overwrite=True))


def test_existing_output_requires_overwrite(media_files: tuple[Path, Path], tmp_path: Path) -> None:
    video, audio = media_files
    output = tmp_path / "existing.mp4"
    output.write_bytes(b"keep")
    with pytest.raises(BeatBloomError, match="already exists"):
        render_video(RenderOptions(video, audio, output))
    assert output.read_bytes() == b"keep"


def test_start_outside_input_duration(media_files: tuple[Path, Path], tmp_path: Path) -> None:
    video, audio = media_files
    with pytest.raises(BeatBloomError, match="outside"):
        render_video(RenderOptions(video, audio, tmp_path / "bad.mp4", start=10))
    assert not (tmp_path / "bad.mp4").exists()


def test_missing_source_fails_before_render(media_files: tuple[Path, Path], tmp_path: Path) -> None:
    video, audio = media_files
    config = write_config(tmp_path, source="absent.wav")
    with pytest.raises(BeatBloomError, match="absent.wav"):
        render_video(RenderOptions(video, audio, tmp_path / "bad.mp4", config=config))


def test_default_config_renders_through_cli(media_files: tuple[Path, Path], tmp_path: Path) -> None:
    video, audio = media_files
    output = tmp_path / "default.mp4"
    assert (
        main(
            [
                "render",
                str(video),
                "--audio",
                str(audio),
                "--duration",
                "0.25",
                "--preset",
                "ultrafast",
                "-o",
                str(output),
            ]
        )
        == 0
    )
    assert probe_video(output).duration == pytest.approx(0.25, abs=1 / 12)


def test_optional_plot_uses_headless_backend(
    media_files: tuple[Path, Path], tmp_path: Path
) -> None:
    pytest.importorskip("matplotlib")
    video, audio = media_files
    plot = tmp_path / "analysis.png"
    render_video(
        RenderOptions(
            video,
            audio,
            tmp_path / "plot.mp4",
            config=write_config(tmp_path),
            start=0.5,
            duration=0.25,
            plot=plot,
            preset="ultrafast",
        )
    )
    assert plot.read_bytes().startswith(b"\x89PNG")


def test_fractional_frame_rate_survives_render(
    media_files: tuple[Path, Path], tmp_path: Path
) -> None:
    _, audio = media_files
    video = tmp_path / "ntsc.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x607080:s=64x48:r=30000/1001:d=1",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        check=True,
        capture_output=True,
    )
    output = tmp_path / "ntsc-output.mp4"
    result = render_video(
        RenderOptions(
            video,
            audio,
            output,
            config=write_config(tmp_path),
            start=0.1001,
            duration=0.4004,
            preset="ultrafast",
        )
    )
    assert result.frames == 12
    assert probe_video(output).fps == Fraction(30000, 1001)


def test_interrupt_preserves_output_and_cleans_children_and_temporary_file(
    media_files: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video, audio = media_files
    output = tmp_path / "interrupted.mp4"
    output.write_bytes(b"keep previous output")

    def interrupt(*_args: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("beatbloom.render.engine.apply_effects", interrupt)
    assert (
        main(
            [
                "render",
                str(video),
                "--audio",
                str(audio),
                "--config",
                str(write_config(tmp_path)),
                "--duration",
                "0.5",
                "--preset",
                "ultrafast",
                "--overwrite",
                "-o",
                str(output),
            ]
        )
        == 130
    )
    assert output.read_bytes() == b"keep previous output"
    assert not list(tmp_path.glob(".interrupted-*.mp4"))
