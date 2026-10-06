"""Command line entry point; expensive libraries are imported only for rendering."""

from __future__ import annotations

import argparse
import logging
import math
import re
from collections.abc import Sequence
from pathlib import Path

from beatbloom import __version__
from beatbloom.config import load_config
from beatbloom.errors import BeatBloomError
from beatbloom.models import RenderOptions


def nonnegative_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("must be a finite number >= 0")
    return parsed


def positive_float(value: str) -> float:
    parsed = nonnegative_float(value)
    if parsed == 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def output_size(value: str) -> tuple[int, int]:
    if not re.fullmatch(r"[0-9]+[xX][0-9]+", value):
        raise argparse.ArgumentTypeError("expected WIDTHxHEIGHT, e.g. 1280x704")
    width, height = (int(part) for part in value.lower().split("x"))
    if width < 2 or height < 2 or width % 2 or height % 2:
        raise argparse.ArgumentTypeError("width and height must be even numbers >= 2 for yuv420p")
    return width, height


def crf_value(value: str) -> int:
    parsed = int(value)
    if not 0 <= parsed <= 51:
        raise argparse.ArgumentTypeError("CRF must be between 0 and 51")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="beatbloom", description="Audio-reactive effects for existing videos."
    )
    parser.add_argument("--version", action="version", version=f"BeatBloom {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    render = commands.add_parser("render", help="Analyze music and render an audio-reactive video")
    render.add_argument("video", type=Path, help="Input video")
    render.add_argument(
        "--audio", type=Path, required=True, help="Original mix to mux in the output"
    )
    render.add_argument("--drive", type=Path, help="Default analysis source (defaults to --audio)")
    render.add_argument("--config", type=Path, help="JSON bands configuration")
    render.add_argument(
        "-o", "--output", type=Path, required=True, help="Output .mp4, .mov or .mkv"
    )
    render.add_argument(
        "--start", type=nonnegative_float, default=0.0, help="Start time in seconds"
    )
    render.add_argument("--duration", type=positive_float, help="Excerpt duration in seconds")
    render.add_argument("--size", type=output_size, help="Center crop and scale, e.g. 1280x704")
    render.add_argument("--crf", type=crf_value, default=16, help="H.264 CRF (default: 16)")
    render.add_argument(
        "--preset",
        default="slow",
        choices=(
            "ultrafast",
            "superfast",
            "veryfast",
            "faster",
            "fast",
            "medium",
            "slow",
            "slower",
            "veryslow",
        ),
        help="x264 encoding preset (default: slow)",
    )
    render.add_argument("--grade", help="FFmpeg video filter chain applied after reactive effects")
    render.add_argument("--plot", type=Path, help="Save analysis plot (requires beatbloom[plot])")
    render.add_argument(
        "--overwrite", action="store_true", help="Replace an existing output on success"
    )
    render.add_argument(
        "--verbose", action="store_true", help="Show diagnostic logging and tracebacks"
    )
    render.add_argument("--quiet", action="store_true", help="Only report errors")
    validate = commands.add_parser(
        "validate", help="Validate a bands configuration without rendering"
    )
    validate.add_argument("config", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    verbose = getattr(args, "verbose", False)
    level = (
        logging.DEBUG
        if verbose
        else logging.ERROR
        if getattr(args, "quiet", False)
        else logging.INFO
    )
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
    logger = logging.getLogger("beatbloom")
    try:
        if args.command == "validate":
            config = load_config(args.config)
            logger.info("Valid configuration: %s bands", len(config.bands))
            return 0
        from beatbloom.render.engine import render_video

        options = RenderOptions(
            video=args.video,
            audio=args.audio,
            output=args.output,
            drive=args.drive,
            config=args.config,
            start=args.start,
            duration=args.duration,
            size=args.size,
            crf=args.crf,
            preset=args.preset,
            grade=args.grade,
            plot=args.plot,
            overwrite=args.overwrite,
        )
        result = render_video(options)
        logger.info("Saved %s (%s frames, %.2f s)", result.output, result.frames, result.duration)
        return 0
    except (BeatBloomError, OSError) as exc:
        logger.error("%s", exc, exc_info=verbose)
        return 1
    except KeyboardInterrupt:
        logger.error("Interrupted; incomplete video output removed")
        return 130


def entrypoint() -> None:
    raise SystemExit(main())
