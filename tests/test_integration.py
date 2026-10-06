from __future__ import annotations

import json
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from beatbloom.cli import main
from beatbloom.config import ProjectConfig
from beatbloom.errors import BeatBloomError
from beatbloom.media import probe_video
from beatbloom.models import RenderOptions
from beatbloom.render.engine import render_video

pytestmark = pytest.mark.integration


def write_config(root: Path, *, source: str | None = None) -> Path:
    signal: dict[str, object] = {
        "feature": "rms",
        "attack_ms": 0,
        "release_ms": 0,
    }
    if source is not None:
        signal["source"] = source
    path = root / "project.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "signals": {"energy": signal},
                "effects": [{"signal": "energy", "effect": "exposure", "amount": 0.5}],
            }
        )
    )
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


def test_signal_source_and_original_audio_mux(
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


def test_preview_without_player_has_requested_fps_and_original_audio(
    media_files: tuple[Path, Path], tmp_path: Path
) -> None:
    video, audio = media_files
    output = tmp_path / "preview.mp4"
    assert (
        main(
            [
                "preview",
                str(video),
                "--audio",
                str(audio),
                "--config",
                str(write_config(tmp_path)),
                "--start",
                "0.2",
                "--duration",
                "0.4",
                "--size",
                "80x60",
                "--no-play",
                "-o",
                str(output),
            ]
        )
        == 0
    )
    info = probe_video(output)
    assert info.fps == Fraction(15)
    assert (info.width, info.height) == (80, 60)
    assert info.duration == pytest.approx(0.4, abs=0.01)
    from beatbloom.media import load_audio

    assert np.max(np.abs(load_audio(output).samples)) > 0.05


def test_render_settings_reuse_analysis_from_analyze_command(
    media_files: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video, audio = media_files
    config = write_config(tmp_path)
    cache = tmp_path / "cache"
    assert main(["analyze", str(audio), "--config", str(config), "--cache-dir", str(cache)]) == 0
    manifests = list((cache / "analysis").glob("*.json"))
    assert len(manifests) == 1

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("warm render must reuse envelopes across all visual settings")

    monkeypatch.setattr("beatbloom.analysis.pipeline.extract_features", forbidden)
    monkeypatch.setattr("beatbloom.analysis.pipeline.load_audio", forbidden)
    payload = json.loads(config.read_text())
    payload["effects"][0]["amount"] = 0.9
    config.write_text(json.dumps(payload))
    result = render_video(
        RenderOptions(
            video,
            audio,
            tmp_path / "warm.mp4",
            config=config,
            cache_dir=cache,
            fps=Fraction(30000, 1001),
            start=0.5,
            duration=0.2002,
            size=(80, 60),
            crf=24,
            preset="ultrafast",
            grade="eq=contrast=1.1",
        )
    )
    assert result.frames == 6
    assert probe_video(result.output).fps == Fraction(30000, 1001)
    assert list((cache / "analysis").glob("*.json")) == manifests


def test_visualizer_only_render_changes_bottom_and_preserves_audio(
    media_files: tuple[Path, Path], tmp_path: Path
) -> None:
    video, audio = media_files
    config = ProjectConfig.model_validate_json(
        json.dumps(
            {
                "schema_version": 2,
                "visualizers": {
                    "music": {
                        "type": "spectrum",
                        "tracks": [{"stem": "mix", "color": "#ff6633"}],
                        "height": 0.4,
                        "bottom": 0,
                        "left": 0,
                        "width": 1,
                        "background_opacity": 0,
                        "spectrum": {"n_fft": 512, "bands": 16},
                    }
                },
            }
        )
    )
    result = render_video(
        RenderOptions(
            video,
            audio,
            tmp_path / "spectrum.mp4",
            start=0.5,
            duration=0.5,
            preset="ultrafast",
            crf=10,
        ),
        config=config,
    )
    assert result.frames == 6
    original = video_pixels(video).reshape(48, 64, 3).astype(float)
    rendered = video_pixels(result.output).reshape(48, 64, 3).astype(float)
    assert np.mean(np.abs(rendered[:25] - original[:25])) < 2
    assert np.mean(np.abs(rendered[32:] - original[32:])) > 6
    from beatbloom.media import load_audio

    assert np.max(np.abs(load_audio(result.output).samples)) > 0.05


def test_visualizer_preview_reuses_analyze_across_fps_size_and_colors(
    media_files: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video, audio = media_files
    path = tmp_path / "visuals.json"
    payload = {
        "schema_version": 2,
        "visualizers": {
            "wave": {"type": "waveform", "height": 0.1, "bottom": 0.02},
            "spectrum": {
                "type": "spectrum",
                "bottom": 0.15,
                "spectrum": {"n_fft": 512, "bands": 16},
            },
        },
    }
    path.write_text(json.dumps(payload))
    cache = tmp_path / "cache"
    assert main(["analyze", str(audio), "--config", str(path), "--cache-dir", str(cache)]) == 0
    manifests = list((cache / "analysis").glob("*.json"))

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("warm visualizers must bypass decoding, waveform and FFT extraction")

    monkeypatch.setattr("beatbloom.analysis.pipeline.load_audio", forbidden)
    monkeypatch.setattr("beatbloom.analysis.visualizers.extract_spectrum", forbidden)
    monkeypatch.setattr("beatbloom.analysis.visualizers.extract_waveform", forbidden)
    payload["visualizers"]["spectrum"]["tracks"] = [{"stem": "mix", "color": "#00aaff"}]
    payload["visualizers"]["wave"]["waveform"] = {"window_seconds": 1, "points": 128}
    path.write_text(json.dumps(payload))
    output = tmp_path / "visual-preview.mp4"
    assert (
        main(
            [
                "preview",
                str(video),
                "--audio",
                str(audio),
                "--config",
                str(path),
                "--cache-dir",
                str(cache),
                "--start",
                "0.2",
                "--duration",
                "0.4",
                "--size",
                "80x60",
                "--fps",
                "30000/1001",
                "--no-play",
                "-o",
                str(output),
            ]
        )
        == 0
    )
    info = probe_video(output)
    assert (info.width, info.height, info.fps) == (80, 60, Fraction(30000, 1001))
    assert list((cache / "analysis").glob("*.json")) == manifests


def test_visualizer_missing_source_fails_before_any_analysis(
    media_files: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video, audio = media_files
    config = ProjectConfig.model_validate_json(
        json.dumps(
            {
                "schema_version": 2,
                "visualizers": {
                    "external": {
                        "type": "waveform",
                        "tracks": [{"source": str(tmp_path / "missing.wav")}],
                    }
                },
            }
        )
    )

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("all visualizer inputs must be checked before analysis")

    monkeypatch.setattr("beatbloom.render.engine.analyze", forbidden)
    with pytest.raises(BeatBloomError, match="missing.wav"):
        render_video(RenderOptions(video, audio, tmp_path / "bad.mp4"), config=config)


def test_interrupt_in_visualizer_preserves_existing_output(
    media_files: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video, audio = media_files
    output = tmp_path / "visual-interrupted.mp4"
    output.write_bytes(b"keep")
    config = ProjectConfig.model_validate_json(
        '{"schema_version":2,"visualizers":{"wave":{"type":"waveform"}}}'
    )

    def interrupt(*_args: object, **_kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("beatbloom.render.engine.apply_visualizers", interrupt)
    with pytest.raises(KeyboardInterrupt):
        render_video(
            RenderOptions(video, audio, output, duration=0.5, overwrite=True), config=config
        )
    assert output.read_bytes() == b"keep"
    assert not list(tmp_path.glob(".visual-interrupted-*.mp4"))
