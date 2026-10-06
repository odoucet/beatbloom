# Changelog

## Unreleased

## 0.2.0 — 2026-10-06

### Added

- `separate`, `analyze` and `preview` commands; renders prepare missing stages.
- Optional Demucs API with six/four-stem models, device overrides and stem aliases.
- SHA256 caches for separated stereo stems, native raw features and envelopes.
- Cache manifests, payload validation, process locks, safe refresh and repair.
- Preview defaults (8 s, 960×540, 15 FPS, ultrafast, CRF 26), ffplay lifecycle
  and saved previews without a player.
- Rational `--fps`, `--cache-dir`, `--refresh`, `--model` and `--device` options.
- Tests for cache reuse/invalidation, corruption, failed refresh, concurrency,
  previews and the real optional Demucs API without weight downloads.

### Changed

- Schema v2 requires named `signals` and independent `effects` mappings.
- Analysis uses native 256-sample timestamps, independent of output FPS.
- Effects, grading, size, FPS and excerpts reuse cached envelopes; envelope
  tuning reuses cached raw features. RMS and loudness share extraction.
- Updated examples, generated schema, configuration docs, roadmap and CI.

### Fixed

- FPS conversion starts each excerpt at zero, preserving preview duration
  when its start falls between source video frames.

### Removed / breaking

- Legacy `bands` JSON, schema v1 and omitted schema versions are rejected.
  Rewrite existing configurations using the v2 examples; no compatibility
  loader or automatic migration remains.
- Frame-rate-dependent envelope sampling. Native-rate smoothing can slightly
  change reactions compared with v0.1; adjust attack/release using a preview.

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
