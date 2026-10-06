# Architecture

BeatBloom v0.2 separates configuration, cached audio processing and rendering.
Importing a module does not start processing or load a separation model.

| Module | Responsibility |
| --- | --- |
| `cli.py` | Arguments, lazy command dispatch, logging and exit codes |
| `config.py` | Schema v2, cross-field validation and relative source paths |
| `models.py` | Typed media, timestamped series and render structures |
| `media.py` | FFmpeg discovery, metadata, mono/stereo decoding and process cleanup |
| `cache.py` | SHA256 identities, file locks and staged atomic publication |
| `separation/base.py` | Injectable backend protocol and cached stem result |
| `separation/demucs.py` | Lazy Demucs API, device selection and float32 WAV output |
| `separation/cache.py` | Separation keys and validated reuse of all model stems |
| `analysis/filters.py` | Frequency isolation |
| `analysis/features.py` | Native 256-sample onset/RMS extraction |
| `analysis/envelopes.py` | Normalization, gate, gamma and attack/release |
| `analysis/cache.py` | Validated NPZ payloads and manifests |
| `analysis/pipeline.py` | Shared source resolution and two-level analysis cache |
| `render/effects.py` | Named mappings and OpenCV effects on float32 RGB |
| `render/engine.py` | Timeline, FFmpeg pipes and atomic video output |
| `preview.py` | ffplay lifecycle |
| `plot.py` | Optional headless diagnostics |

## Cached audio processing

`separate` calls the separation stage. `analyze` calls the common analysis
pipeline. Both `preview` and `render` call that same pipeline before encoding.
Signals resolve to existing source files, the original mix/default drive, or
cached Demucs stems. Model and Torch imports happen only on a separation miss.
Package versions are read through distribution metadata without loading Torch.

The separation key includes the original file hash, backend versions and model
options. All stems are committed together; choosing another stem reuses that
separation. Raw feature keys include the actual source hash, frequency filter,
feature kind, native grid, algorithm version and NumPy/SciPy/Librosa versions.
RMS and loudness share raw RMS data. Normalized envelope keys additionally
include gate, gamma, percentile and smoothing settings.

Visual mappings and all video options are excluded from analysis keys. Signal
names link cached envelopes through a small analysis manifest. Every cached
series is validated for shape, type, finite values and increasing timestamps;
manifest hashes detect payload corruption. NPZ loading forbids pickle. Stem
manifests verify hashes, stereo rate, float format and aligned lengths.

Cache files are produced in a temporary directory on the cache filesystem,
then published under a per-key cross-process lock. Refresh keeps the previous
entry until its replacement is complete. Locks are always acquired from
signal to feature; separation completes before signal processing begins.

Full-track audio is decoded only on extraction misses (or explicitly for
plots). Warm runs hash source files and probe the soundtrack duration; unusual
files without reliable duration metadata may require decoding that mix.
Persistent artifacts live under `stems/`, `features/`, `signals/`, `analysis/`
and `locks/` in the configured user cache root.

## Rendering and preview

`Signal.at(timestamp)` linearly interpolates native audio timestamps. The frame
loop only maps signals and processes pixels. Full-track normalization remains
identical for a preview and final render, regardless of FPS or excerpt.
The original mix controls audio timing. All sources must align at time zero.

FFmpeg decodes raw RGB frames at the chosen rational CFR. OpenCV applies
reactive effects; another FFmpeg process grades, encodes H.264 and muxes the
original mix as AAC. File-backed stderr prevents pipe deadlocks. Both children
are checked, terminated when necessary and reaped on every exit path. The
output replaces its target only after successful encoding.

Preview uses the same renderer with shorter, smaller, lower-FPS defaults.
A temporary directory exists throughout playback and is removed afterwards,
including interruption. An explicit output persists. ffplay is checked before
processing unless `--no-play` is selected.

## Verification

Synthetic tests cover content-based invalidation, corruption recovery,
concurrency, failed refresh, source routing and mapping. Real FFmpeg tests
check effects, soundtrack muxing, rational FPS, excerpts, resizing, plots,
previews and output preservation. Optional backend tests run the real Demucs
API with its tiny untrained test model, requiring no production weights.
