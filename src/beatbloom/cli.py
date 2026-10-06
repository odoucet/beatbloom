"""Command line entry points; separation and rendering libraries are imported lazily."""

from __future__ import annotations

import argparse
import json
import logging
import math
import re
import tempfile
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path

from pydantic import ValidationError

from beatbloom import __version__
from beatbloom.config import ProjectConfig, load_config
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


def frame_rate(value: str) -> Fraction:
    try:
        parsed = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise argparse.ArgumentTypeError("expected positive FPS, e.g. 24 or 30000/1001") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("frame rate must be positive")
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


def _processing_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, help="Schema v2 JSON with signals and effects")
    parser.add_argument("--cache-dir", type=Path, help="Persistent cache (default: OS user cache)")
    parser.add_argument("--refresh", action="store_true", help="Recompute required cache entries")
    parser.add_argument(
        "--model", choices=("htdemucs_6s", "htdemucs"), help="Override Demucs model"
    )
    parser.add_argument("--device", help="Override Demucs device: auto, cpu, cuda[:N] or mps")
    logging_flags = parser.add_mutually_exclusive_group()
    logging_flags.add_argument("--verbose", action="store_true", help="Diagnostic logging")
    logging_flags.add_argument("--quiet", action="store_true", help="Only report errors")


def _render_arguments(parser: argparse.ArgumentParser, *, preview: bool) -> None:
    parser.add_argument("video", type=Path, help="Input video")
    parser.add_argument(
        "--audio", type=Path, required=True, help="Original mix to mux in the output"
    )
    parser.add_argument("--drive", type=Path, help="Default signal source (defaults to --audio)")
    _processing_arguments(parser)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=not preview,
        help="Output .mp4, .mov or .mkv (preview defaults to a temporary file)",
    )
    parser.add_argument(
        "--start", type=nonnegative_float, default=0.0, help="Start time in seconds"
    )
    parser.add_argument(
        "--duration",
        type=positive_float,
        default=8.0 if preview else None,
        help="Excerpt duration in seconds (preview default: 8)",
    )
    parser.add_argument(
        "--size",
        type=output_size,
        default=(960, 540) if preview else None,
        help="Center crop and scale; preview default: 960x540",
    )
    parser.add_argument(
        "--fps",
        type=frame_rate,
        default=Fraction(15) if preview else None,
        help="Output FPS; render defaults to source, preview to 15",
    )
    parser.add_argument(
        "--crf",
        type=crf_value,
        default=26 if preview else 16,
        help="H.264 CRF (render default: 16; preview: 26)",
    )
    parser.add_argument(
        "--preset",
        default="ultrafast" if preview else "slow",
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
        help="x264 preset (render default: slow; preview: ultrafast)",
    )
    parser.add_argument("--grade", help="FFmpeg filters applied after reactive effects")
    parser.add_argument("--plot", type=Path, help="Save analysis plot (requires beatbloom[plot])")
    parser.add_argument(
        "--overwrite", action="store_true", help="Replace existing outputs on success"
    )
    if preview:
        parser.add_argument(
            "--no-play", action="store_true", help="Save without ffplay; requires -o"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="beatbloom", description="Audio-reactive video effects.")
    parser.add_argument("--version", action="version", version=f"BeatBloom {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    _render_arguments(
        commands.add_parser("render", help="Render an audio-reactive video"), preview=False
    )
    _render_arguments(
        commands.add_parser("preview", help="Render a short preview and open ffplay"), preview=True
    )
    analyze = commands.add_parser("analyze", help="Cache full-track features and signal envelopes")
    analyze.add_argument("audio", type=Path)
    analyze.add_argument("--drive", type=Path, help="Default signal source (defaults to audio)")
    _processing_arguments(analyze)
    separate = commands.add_parser("separate", help="Separate and cache all Demucs stems")
    separate.add_argument("audio", type=Path)
    _processing_arguments(separate)
    validate = commands.add_parser("validate", help="Validate schema v2 without reading media")
    validate.add_argument("config", type=Path)
    return parser


def _project_config(args: argparse.Namespace) -> ProjectConfig:
    config = load_config(args.config)
    overrides = {
        name: getattr(args, name)
        for name in ("model", "device")
        if getattr(args, name, None) is not None
    }
    if overrides:
        payload = config.model_dump(mode="json")
        payload["separation"].update(overrides)
        try:
            config = ProjectConfig.model_validate_json(json.dumps(payload))
        except ValidationError as exc:
            raise BeatBloomError(f"Invalid separation options: {exc}") from exc
    return config


def _render_options(args: argparse.Namespace, output: Path) -> RenderOptions:
    return RenderOptions(
        video=args.video,
        audio=args.audio,
        output=output,
        drive=args.drive,
        config=args.config,
        start=args.start,
        duration=args.duration,
        size=args.size,
        fps=args.fps,
        crf=args.crf,
        preset=args.preset,
        grade=args.grade,
        plot=args.plot,
        overwrite=args.overwrite,
        cache_dir=args.cache_dir,
        refresh=args.refresh,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "preview" and args.no_play and args.output is None:
        parser.error("preview --no-play requires --output")
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
    logger.setLevel(level)
    try:
        config = _project_config(args)
        if args.command == "validate":
            logger.info(
                "Valid configuration: %s signals, %s effects",
                len(config.signals),
                len(config.effects),
            )
        elif args.command == "separate":
            from beatbloom.separation.cache import separate_audio

            stems = separate_audio(
                args.audio, config.separation, cache_dir=args.cache_dir, refresh=args.refresh
            )
            logger.info("Stems %s: %s", "reused" if stems.cached else "separated", stems.manifest)
            for name, path in stems.stems.items():
                logger.info("%s: %s", name, path)
        elif args.command == "analyze":
            from beatbloom.analysis.pipeline import analyze

            result = analyze(
                args.audio, config, drive=args.drive, cache_dir=args.cache_dir, refresh=args.refresh
            )
            logger.info(
                "Analysis manifest: %s (%s/%s envelopes reused, %s raw features reused)",
                result.manifest,
                result.signal_hits,
                len(result.signals),
                result.feature_hits,
            )
        else:
            from beatbloom.render.engine import render_video

            def render_to(output: Path) -> None:
                result = render_video(_render_options(args, output), config=config)
                logger.info(
                    "Saved %s (%s frames, %.2f s)", result.output, result.frames, result.duration
                )
                if args.command == "preview" and not args.no_play:
                    from beatbloom.preview import play_preview

                    play_preview(result.output)

            if args.command == "preview" and not args.no_play:
                from beatbloom.preview import require_player

                require_player()
            if args.output is None:
                with tempfile.TemporaryDirectory(prefix="beatbloom-preview-") as directory:
                    render_to(Path(directory) / "preview.mp4")
            else:
                render_to(args.output)
        return 0
    except (BeatBloomError, OSError) as exc:
        logger.error("%s", exc, exc_info=verbose)
        return 1
    except KeyboardInterrupt:
        logger.error("Interrupted; incomplete output and child processes cleaned up")
        return 130


def entrypoint() -> None:
    raise SystemExit(main())
