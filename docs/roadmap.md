# Roadmap

## 0.1 — usable open-source foundation

- [x] `src/` package and `beatbloom render` CLI
- [x] Validated v1 configuration and compatibility with existing bands
- [x] Typed interfaces and modular analysis/effects/render pipeline
- [x] Original bloom, exposure, saturation, zoom and brightness
- [x] Full-track normalization and optional analysis plot
- [x] FFmpeg checks, useful errors, cleanup and protected output
- [x] uv lockfile, Ruff, mypy, pytest, Make and pre-commit
- [x] GitHub CI, installation docs, examples and MIT license
- [ ] Add a representative real-world demo from redistributable media

## 0.2 — reusable analysis and fast iteration

- [ ] `separate` and `analyze` commands; `render` fills in missing stages
- [ ] Optional Demucs backend, beginning with `htdemucs_6s`
- [ ] Stem aliases instead of manually assembled WAV paths
- [ ] Content-addressed stem cache (audio hash, model, version and options)
- [ ] Timestamped analysis independent of video frame rate
- [ ] Analysis cache keys exclude visual mappings
- [ ] Separate named signals and effect mappings in a versioned schema
- [ ] Easy preview defaults and ffplay integration

## 0.3 — audio visualizers

- [ ] Bottom-of-frame waveform and spectrum
- [ ] Multi-stem spectrum and configurable colors/layout/opacity
- [ ] Cached STFT logarithmic bands and visualizer envelopes

## 0.4 — creative workflow

- [ ] Dedicated `.cube` LUT option and safe filter-path handling
- [ ] `grade-preview` without re-encoding
- [ ] Presets, masks and blending
- [ ] Additional effects, beginning with shake and RGB split

Release tags and PyPI publication will be managed separately from code
development. Do not advertise installation from PyPI until a distribution
has actually been published.
