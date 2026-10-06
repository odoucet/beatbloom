# Roadmap

## 0.1 — usable open-source foundation

- [x] `src/` package and `beatbloom render` CLI
- [x] Validated v1 configuration (retired in v0.2)
- [x] Typed interfaces and modular analysis/effects/render pipeline
- [x] Original bloom, exposure, saturation, zoom and brightness
- [x] Full-track normalization and optional analysis plot
- [x] FFmpeg checks, useful errors, cleanup and protected output
- [x] uv lockfile, Ruff, mypy, pytest, Make and pre-commit
- [x] GitHub CI, installation docs, examples and MIT license
- [ ] Add a representative demo from redistributable media

## 0.2 — reusable analysis and fast iteration

- [x] `separate` and `analyze`; `render` fills missing stages
- [x] Optional Demucs API, `htdemucs_6s` and `htdemucs`
- [x] Stem aliases instead of manually assembled WAV paths
- [x] Content-addressed stem cache (audio, model, versions, options)
- [x] Native timestamped analysis independent of video FPS
- [x] Raw feature and normalized envelope caches, excluding visual mappings
- [x] Named signals and effect mappings in schema v2; v1 removed
- [x] Preview defaults, optional persistent output and ffplay integration
- [x] Corruption recovery, process locks and safe refresh

## 0.3 — audio visualizers

- [x] Bottom-of-frame waveform and spectrum
- [x] Multi-stem spectrum and configurable colors/layout/opacity
- [x] Cached STFT logarithmic bands and visualizer envelopes

- [x] Visualizer-only projects and unchanged v0.2 configuration support
- [x] Reproducible synthetic multi-instrument demo

## 0.4 — creative workflow

- [x] Offline editor preparation: generated contract, standalone HTML, synthetic still preview
- [x] English editor, local media drops, video still selection and preparation config import
- [ ] Refine the editor with real project fixtures and more usable preset controls
- [ ] Export cached analysis snapshots from Python for a media-grounded offline preview
- [ ] Dedicated `.cube` LUT option and safe filter-path handling
- [ ] `grade-preview` without re-encoding
- [ ] Presets, masks and blending
- [ ] Additional effects, beginning with shake and RGB split

GitHub releases and PyPI publication remain separate maintainer actions.
