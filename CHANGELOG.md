# Changelog

## Unreleased

## 0.1.0 — 2026-10-06

### Added

- Installable Python package with `beatbloom render`, `beatbloom validate`
  and `python -m beatbloom` entry points.
- Strict JSON configuration validation, typed models and modular analysis,
  mapping and rendering.
- Bloom, exposure, saturation, zoom and brightness from the original prototype.
- Full-track normalization, source reuse within a run, Opus decoding through
  FFmpeg, excerpt rendering, crop/resize and optional headless plots.
- Selectable H.264 encoder preset and the existing FFmpeg grade filter chain.
- Explicit FFmpeg dependency checks, useful failures, process cleanup and
  atomic video output with opt-in overwrite.
- uv packaging/lockfile, Ruff, mypy, pytest, pre-commit, Make targets and CI.
- MIT license, contributor guide, configuration reference and examples.
