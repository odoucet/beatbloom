"""Generate original synthetic audio, a background video and a ready-to-render configuration.

Usage: uv run python examples/make_demo.py demo
Then:  uv run beatbloom preview demo/video.mp4 --audio demo/mix.wav \
         --config demo/visualizers.json --no-play -o demo/preview.mp4
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
import soundfile as sf

from beatbloom.config import SAMPLE_RATE
from beatbloom.media import require_tools


def create_demo(destination: Path) -> None:
    require_tools()
    destination.mkdir(parents=True, exist_ok=True)
    duration = 8
    times = np.arange(SAMPLE_RATE * duration, dtype=np.float64) / SAMPLE_RATE
    notes = [261.63, 329.63, 392.0, 523.25, 440.0, 392.0, 329.63, 293.66]
    piano = np.zeros_like(times)
    drums = np.zeros_like(times)
    bass = np.zeros_like(times)
    rng = np.random.default_rng(42)
    noise = rng.normal(0, 1, len(times))
    for beat in range(duration * 2):
        local = times - beat / 2
        active = (local >= 0) & (local < 0.48)
        phase = local[active]
        note = notes[beat % len(notes)]
        piano[active] += (
            0.18
            * np.exp(-phase * 8)
            * (np.sin(2 * np.pi * note * phase) + 0.3 * np.sin(4 * np.pi * note * phase))
        )
        drums[active] += 0.24 * np.exp(-phase * 24) * np.sin(2 * np.pi * 65 * phase)
        drums[active] += 0.025 * np.exp(-phase * 70) * noise[active]
        bass[active] += (
            0.14
            * np.sin(2 * np.pi * (65.41 if beat % 4 < 2 else 87.31) * phase)
            * np.minimum(1, phase * 40)
            * np.exp(-phase * 3)
        )
    tracks = {"piano": piano, "drums": drums, "bass": bass}
    for name, samples in {**tracks, "mix": piano + drums + bass}.items():
        sf.write(
            destination / f"{name}.wav", samples.astype(np.float32), SAMPLE_RATE, subtype="FLOAT"
        )
    yy, xx = np.mgrid[:540, :960]
    gradient = (xx / 960 * 0.4 + yy / 540 * 0.6)[..., None]
    background = np.asarray(
        np.array([7, 15, 27]) + gradient * np.array([12, 19, 31]), dtype=np.uint8
    )
    cv2.putText(
        background,
        "BEATBLOOM",
        (58, 124),
        cv2.FONT_HERSHEY_SIMPLEX,
        2.2,
        (236, 239, 242),
        3,
        cv2.LINE_AA,
    )
    cv2.putText(
        background,
        "MUSIC IN MOTION   /   v0.3",
        (61, 163),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (156, 179, 202),
        1,
        cv2.LINE_AA,
    )
    cv2.line(background, (61, 189), (899, 189), (80, 101, 120), 1)
    cv2.putText(
        background,
        "WAVEFORMS",
        (61, 247),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (156, 179, 202),
        1,
        cv2.LINE_AA,
    )
    colors = {"piano": "#65d4ff", "drums": "#ffaa66", "bass": "#c498ff"}
    for index, name in enumerate(tracks):
        color = tuple(int(colors[name][part : part + 2], 16) for part in (5, 3, 1))
        cv2.putText(
            background,
            name.upper(),
            (61 + index * 283, 391),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )
    image = destination / "background.png"
    if not cv2.imwrite(str(image), background):
        raise OSError(f"Cannot write {image}")
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image),
            "-t",
            str(duration),
            "-r",
            "24",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-pix_fmt",
            "yuv420p",
            str(destination / "video.mp4"),
        ],
        check=True,
    )
    selection = [{"source": f"{name}.wav", "color": colors[name]} for name in tracks]
    config = {
        "schema_version": 2,
        "visualizers": {
            "waveforms": {
                "type": "waveform",
                "tracks": selection,
                "layout": "stacked",
                "left": 0.06,
                "width": 0.88,
                "height": 0.21,
                "bottom": 0.30,
                "line_width": 1,
                "opacity": 0.9,
                "fill_opacity": 0.14,
                "background_opacity": 0.05,
                "waveform": {"window_seconds": 3},
            },
            "spectra": {
                "type": "spectrum",
                "tracks": selection,
                "layout": "side_by_side",
                "left": 0.06,
                "width": 0.88,
                "height": 0.23,
                "bottom": 0.03,
                "opacity": 0.9,
                "background_opacity": 0.05,
                "spectrum": {
                    "n_fft": 2048,
                    "bands": 48,
                    "low": 40,
                    "high": 7000,
                    "gamma": 1.3,
                    "floor_db": -50,
                },
            },
        },
    }
    (destination / "visualizers.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Ready: {destination / 'video.mp4'}, mix.wav and visualizers.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, nargs="?", default=Path("demo"))
    create_demo(parser.parse_args().destination)
