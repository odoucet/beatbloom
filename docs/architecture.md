# Architecture

The v0.1 package has three boundaries: validated configuration, named analysis
signals and video rendering. No module starts work when imported.

| Module | Responsibility |
| --- | --- |
| `cli.py` | Argument parsing, logging and actionable exit codes |
| `config.py` | Pydantic configuration validation and relative source resolution |
| `models.py` | Typed audio, video, signal, effect and render structures |
| `media.py` | FFmpeg discovery, probing, audio decoding and child cleanup |
| `analysis/filters.py` | Frequency isolation |
| `analysis/envelopes.py` | Normalization, gate, gamma and attack/release |
| `analysis/features.py` | Complete-track onset/RMS analysis and source reuse |
| `render/effects.py` | Per-frame mapping and OpenCV effects on float32 RGB |
| `render/engine.py` | Excerpt selection, pipe lifecycle, encoding and atomic output |
| `plot.py` | Optional headless diagnostics |

The renderer receives named `Signal` objects and uses `signal.at(timestamp)`.
It does not load stems or extract features inside the frame loop. Mapping
is separate from image processing even though schema v1 stores mappings in
each band, matching the original script.

The original audio mix controls the output timeline. `--drive` and per-band
`source` files only control reactions. Every signal is normalized over its
own full source track before the renderer selects an excerpt. Fractional
video rates are carried as `Fraction` objects and passed to FFmpeg exactly.

FFmpeg decodes input video into raw RGB frames. OpenCV applies effects on
float32 data; a second FFmpeg process encodes H.264 and muxes the original
music as AAC. Stderr is written to temporary files to avoid pipe deadlocks.
Both processes are checked, terminated if needed and reaped on every exit
path. Final video output is replaced only after successful encoding.

v0.1 retains frame-rate-dependent envelope sampling for compatibility with
the prototype. v0.2 will move cached features to their own timestamp grid,
separate signal definitions from mapping, and add automatic source resolution.
Those additions can reuse the signal interface and effect renderer.

The integration tests generate tiny media fixtures with FFmpeg. They verify
actual visual changes, original audio muxing, excerpts, resize, plots,
missing sources and preservation of existing output after an encoder error.
