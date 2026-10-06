# BeatBloom

Audio-reactive effects for existing videos: bloom, exposure, saturation, zoom
and brightness driven by music, plus waveform and logarithmic spectrum overlays.

**Version 0.3.0** adds bottom-of-frame waveform and spectrum visualizers,
including multiple instrument tracks, layouts, colors and opacity. Optional
Demucs separation and full-track analysis remain cached independently of style.
`analyze`, `preview` and `render` share the same full-track analysis.
The original music mix is always used in the output.

## Requirements

- Python 3.10–3.14.
- FFmpeg and ffprobe on `PATH`, with H.264 (`libx264`) and AAC encoders.
- ffplay for previews that open a player. `--no-play -o preview.mp4` works
  without ffplay or a graphical display.
- Demucs/PyTorch only when using instrument stems; model weights download
  on the first separation. A CPU works; CUDA can speed up separation.

Install FFmpeg with your system package manager, for example `apt install ffmpeg`
on Debian/Ubuntu or `brew install ffmpeg` on macOS. On Windows, install an
FFmpeg build and add its `bin` directory to `PATH`.

## Install

```bash
git clone https://github.com/odoucet/beatbloom.git
cd beatbloom
uv sync --locked --extra plot
uv run beatbloom --version
```

For automatic stem separation:

```bash
uv sync --locked --extra plot --extra demucs
```

With pip in a virtual environment, clone the repository and run:

```bash
python -m pip install ".[plot]"
# Optional instrument separation:
python -m pip install ".[demucs,plot]"
```

BeatBloom is not yet published on PyPI. The core installation analyzes mixes
and existing audio files without installing PyTorch. Use `uv run --extra demucs`
for commands that need stems.

## Preview and render

```bash
uv run beatbloom preview video.mp4 --audio morceau.opus   --config examples/basic.json --start 60
```

Preview defaults: 8 seconds, 960×540, 15 FPS, `ultrafast`, CRF 26.
The video is kept in a temporary directory while ffplay is open, then removed.
To save it, supply `-o`; to save without opening a player:

```bash
uv run beatbloom preview video.mp4 --audio morceau.opus   --config examples/basic.json --start 60 --no-play -o preview.mp4
```

A full-quality render uses the input video frame rate, `slow` and CRF 16:

```bash
uv run beatbloom render video.mp4 --audio morceau.opus   --config examples/basic.json -o final.mp4
```

If no configuration is supplied, global loudness controls brightness and
onsets in the 400–2000 Hz range drive bloom, exposure and saturation.
`--drive drums.wav` changes the default signal source while keeping
`--audio` as the soundtrack. Explicit `stem: "mix"` always uses the mix.

Both commands support `--start`, `--duration`, `--size`, `--fps` (including
`30000/1001`), `--grade`, `--plot`, `--cache-dir`, `--refresh` and `--overwrite`.
For example:

```bash
uv run --extra plot beatbloom render video.mp4 --audio morceau.opus   --config examples/subtle.json --start 60 --duration 8   --size 1280x720 --fps 24 --plot analysis.png   --grade "curves=preset=increase_contrast,vignette=PI/5" -o excerpt.mp4
```

`--start` selects the same absolute position in video and audio. Duration is
limited to their common remaining duration. Analysis and percentile
normalization always use the **complete source tracks**, even for previews.
Native audio timestamps make reactions independent of video FPS.

Existing outputs need `--overwrite`. Encoding completes in a temporary file;
failed or interrupted renders preserve an existing video. A requested plot
is saved separately before video encoding. A saved preview remains available
if the player fails.

Output: MP4, MOV or MKV with H.264 video and AAC audio. Input video audio is
replaced by `--audio`. Output is CFR; fractional FPS are preserved.
Rotation metadata is not applied. Dimensions must be even; `--size` scales
and center-crops to fit.

## Waveforms and spectra

```bash
uv run beatbloom preview video.mp4 --audio morceau.opus \
  --config examples/visualizers.json --start 60

# Four instrument spectra from Demucs, plus the mix waveform:
uv run --extra demucs beatbloom preview video.mp4 --audio morceau.opus \
  --config examples/visualizers-demucs.json --start 60
```

Add the optional `visualizers` object to any schema v2 project. A minimal
visualizer-only configuration needs no reactive signals or effects:

```json
{
  "schema_version": 2,
  "visualizers": {
    "music": {
      "type": "spectrum",
      "tracks": [{"stem": "mix", "color": "#65d4ff"}],
      "height": 0.18,
      "bottom": 0.03,
      "opacity": 0.9
    }
  }
}
```

Use `type: "waveform"` for a moving signed peak waveform centered on the
current audio time. Spectrum bars use logarithmic frequency bands and native
attack/release envelopes. Both normalize over the complete track; previews
and final renders use the same data.

Tracks can select `stem` aliases or `source` files. The default track explicitly
uses the mix; a track without either selector uses `--drive`, then the mix.
Choose `overlay`, `stacked` or `side_by_side` for multiple tracks. Region sizes
and positions are fractions of the output frame, so resizing keeps the layout.
Each track has its own RGB color; opacity, gain, background and gaps are configurable.
Overlays are drawn after reactive effects and before the FFmpeg grade filter.

`analyze` prepares visualizer data too. Color, layout, opacity, gain, waveform
window, points, video size, FPS and excerpts reuse the caches. Spectrum envelope
tuning reuses raw log bands. Changing FFT size, band count or frequency range
recomputes the spectrum. Existing v0.2 JSON remains valid; no overlay is added
unless declared. See [the visualizer reference](docs/configuration.md#visualizers).

Try an entirely synthetic, reproducible demo:

```bash
uv run python examples/make_demo.py demo
uv run beatbloom preview demo/video.mp4 --audio demo/mix.wav \
  --config demo/visualizers.json --no-play -o demo/preview.mp4
```

The generator creates original piano-like tones, drums, bass and a background
video. It uses external-file tracks, so no Demucs installation or weights are
needed. `demo/` is ignored by Git. The script replaces its generated inputs
when run again; BeatBloom still protects the preview output unless `--overwrite` is used.

## Stems and reusable analysis

```bash
# Prepare all six stems once (or let analyze/render do it automatically):
uv run --extra demucs beatbloom separate morceau.opus

# Cache only the signals declared in the configuration:
uv run --extra demucs beatbloom analyze morceau.opus --config examples/demucs.json

# Reuse those signals while adjusting effects and trying excerpts:
uv run --extra demucs beatbloom preview video.mp4 --audio morceau.opus   --config examples/demucs.json --start 60
uv run --extra demucs beatbloom render video.mp4 --audio morceau.opus   --config examples/demucs.json -o final.mp4
```

`examples/demucs.json` uses `stem: "piano"`, `"other"` and `"drums"`.
The default `htdemucs_6s` model also produces bass, vocals and guitar.
`htdemucs` produces four stems: drums, bass, vocals and other. Choose a model
and device in JSON or override them with `--model` and `--device cpu|cuda|mps`.
Automatic device selection uses CUDA when available, otherwise CPU.
Piano separation can contain leakage; listen to the stem before tuning effects.

Caches live in the OS user cache directory (`beatbloom`); `--cache-dir .cache/beatbloom`
selects a project cache. Logs and the analysis manifest show their locations.

- Stem keys include input file content, model, backend versions and separation options.
- Feature keys include source content, extraction parameters and numerical library versions.
- Envelope keys include the feature key and normalization/smoothing settings.
- Visualizer peak/log-band caches and their envelopes use separate namespaces;
  display settings do not affect their identities.
- Effect weights, grading, video, size, FPS and excerpt do not invalidate analysis.
- Changing gate, gamma or attack/release reuses raw features.
- Every hit verifies manifests and payload hashes. Invalid entries rebuild.
- `--refresh` recomputes the required stages; a failed refresh keeps valid old entries.

Cache reads use locks; concurrent processes share completed entries. Cached stems
can be reused without loading a model; the Demucs extra must still be installed.
Deleting the cache simply causes recomputation. The cache contains audio stems,
so choose its location accordingly. Model weights are managed by Demucs separately.

## JSON v2

**Legacy `bands` JSON and schema v1 are no longer supported.**
Use `schema_version: 2`, named `signals` with an independent `effects` list,
and/or named `visualizers`:

```json
{
  "schema_version": 2,
  "signals": {
    "kick": {"stem": "drums", "low": 40, "high": 120, "feature": "rms"}
  },
  "effects": [
    {"signal": "kick", "effect": "zoom", "amount": 0.006}
  ]
}
```

Signals and visualizer tracks can also use `source: "../stems/drums.wav"`; these files must already
be aligned with the mix. Relative paths resolve against the JSON file.
Unknown keys, invalid values and undefined signal references are rejected.
Validation reads no media and downloads no models:

```bash
uv run beatbloom validate examples/basic.json
uv run beatbloom preview --help
```

See [the configuration reference](docs/configuration.md) and
[the architecture](docs/architecture.md).

## Development

```bash
make install
make check
make build
uv run pre-commit install
```

Without Make: `uv sync --locked --extra plot --dev`, then `uv run ruff format --check .`,
`uv run ruff check .`, `uv run mypy`, `uv run pytest` and `uv build`.
`make install-demucs` additionally installs the separation extra.

Tests use synthetic media, real FFmpeg rendering and a deterministic test backend
for cache behavior. Visualizer tests cover frequency placement, peak retention,
native smoothing, RGB/opacity, layouts, resizing and warm-cache previews. An optional real Demucs/PyTorch smoke test uses the official
tiny untrained model, without downloading production weights:

```bash
uv run --extra demucs pytest -m demucs_runtime
```

CI checks core tests on Python 3.10, 3.12 and 3.14, portability, packaging and
that optional CPU backend. No media or model weights are committed.
See [CONTRIBUTING.md](CONTRIBUTING.md) and [the roadmap](docs/roadmap.md).

## License

[MIT](LICENSE), copyright Olivier Doucet. Dependencies, media and downloaded
model weights retain their own licenses.
