# BeatBloom

Audio-reactive video effects driven by music analysis.

BeatBloom post-processes an existing video with bloom, exposure, saturation,
zoom and brightness driven by frequency bands in your music. Analyze the mix
or individual instrument stems, then mux the original music into the output.

**Version 0.1.0:** a packaged and tested version of the original prototype.
Automatic source separation, persistent analysis caching, visualizers and a
dedicated preview command are planned; see [the roadmap](docs/roadmap.md).

## Requirements

- Python 3.10–3.14.
- FFmpeg and ffprobe on `PATH`, with the `libx264` and AAC encoders.
- A video and a music file. FFmpeg-supported audio formats such as WAV, MP3,
  FLAC and Opus can be decoded without additional audio tools.

Install FFmpeg with your system package manager (for example `apt install ffmpeg`
on Debian/Ubuntu or `brew install ffmpeg` on macOS). On Windows, install an
FFmpeg build and add its `bin` directory to `PATH`.

## Install from this repository

```bash
git clone https://github.com/odoucet/beatbloom.git
cd beatbloom
uv sync --locked --extra plot
uv run beatbloom --version
```

Or install with pip in a virtual environment:

```bash
python -m pip install "git+https://github.com/odoucet/beatbloom.git"
```

For plots with pip, clone the repository and run `python -m pip install ".[plot]"`.
The project is not yet published on PyPI.

## Render

```bash
uv run beatbloom render video.mp4 \
  --audio morceau.opus \
  --config examples/basic.json \
  -o final.mp4
```

If no configuration is supplied, BeatBloom uses global brightness and
onsets in the 400–2000 Hz range to drive bloom, exposure and saturation.

Analyze a different track while retaining the original mix in the output:

```bash
uv run beatbloom render video.mp4 --audio morceau.opus \
  --drive drums.wav --config examples/subtle.json -o final.mp4
```

Render a short excerpt, resize it and save an analysis plot:

```bash
uv run --extra plot beatbloom render video.mp4 --audio morceau.opus \
  --config examples/basic.json --start 60 --duration 8 \
  --size 960x540 --preset ultrafast --crf 26 \
  --plot analysis.png -o test.mp4
ffplay test.mp4
```

Analysis and percentile normalization always use each **complete source track**.
Rendering an excerpt does not normalize that excerpt separately. `--start`
selects the same absolute position in both the video and the audio; the
default duration is the remaining common duration of the two inputs.

Use `--grade` for FFmpeg filters applied after the reactive effects:

```bash
uv run beatbloom render video.mp4 --audio morceau.opus \
  --grade "curves=preset=increase_contrast,vignette=PI/5" -o graded.mp4
```

Existing outputs are protected. Add `--overwrite` to replace them after a
successful render. The video is encoded to a temporary file in the output
directory; failed or interrupted renders remove that file and preserve an
existing output. A requested plot is saved separately before video encoding.

Output containers: MP4, MOV and MKV, with H.264 video and AAC audio. Video
input audio is discarded in favor of `--audio`. Output is CFR at the probed
average frame rate (fractional rates such as 30000/1001 are preserved).
Input rotation metadata is not applied in v0.1. Dimensions must be even for
YUV 4:2:0; `--size` center-crops and scales to even dimensions.

```bash
uv run beatbloom render --help
uv run beatbloom validate examples/basic.json
python -m beatbloom --version
```

## Configuration and existing Demucs stems

The original `{"bands": [...]}` format is supported. Paths in `source` are
resolved relative to the JSON file, not the current working directory.
Unknown keys, effects and invalid ranges produce explicit validation errors.
See [the configuration reference](docs/configuration.md).

For v0.1, run Demucs separately in its own environment:

```bash
uv venv .venv-demucs --python 3.11
uv pip install --python .venv-demucs/bin/python demucs
.venv-demucs/bin/demucs -n htdemucs_6s -o separated morceau.opus
uv run beatbloom render video.mp4 --audio morceau.opus \
  --config examples/demucs.json -o final.mp4
```

On Windows use `.venv-demucs\Scripts\python.exe` and
`.venv-demucs\Scripts\demucs.exe`. The example expects `morceau.opus` and
`separated/htdemucs_6s/morceau/{piano,other,drums}.wav` in the repository root;
edit the paths for a different track name. Demucs, PyTorch and model downloads
are optional external tools and are not BeatBloom runtime dependencies.

## Development

```bash
make install
make check
make build
uv run pre-commit install
```

`make check` runs Ruff formatting/linting, strict mypy and pytest. Integration
tests generate their own tiny audio/video inputs and perform real FFmpeg
renders. No copyrighted media or model weights are included. Tests needing
FFmpeg skip locally when the executables are unavailable; CI installs FFmpeg.

Windows users without Make can run the equivalent commands:

```bash
uv sync --locked --all-extras --dev
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv build
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [the architecture](docs/architecture.md).

## License

[MIT](LICENSE), copyright Olivier Doucet. Third-party dependencies, music,
videos and externally downloaded model weights retain their own licenses.
