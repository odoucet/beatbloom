# Offline editor preparation

Status: preparatory prototype on top of BeatBloom 0.3.0. Schema remains v2.

## User workflow

1. Double-click `editor/beatbloom-editor.html` in a desktop browser.
2. Use the built-in synthetic scene, or drop an image/video anywhere in the window.
   The preview uses native dimensions and aspect ratio. Videos remain paused;
   select a still with the **Video frame** slider.
3. Drop an existing config or an analysis preparation JSON to restore all settings.
   One media file and one JSON can be dropped together; file-picker buttons also work.
4. Adjust positions, sizes, colors, layouts, opacity and reactive effect mappings.
5. Simulate different normalized signal levels to inspect effect intensity.
6. Download `beatbloom.json`, validate it with Python, and render normally.

All CSS, JavaScript, schema, defaults and artwork are embedded in one HTML file.
There are no CDN assets, remote fonts, fetches, service workers or web server.
The English interface includes the project URL in its footer. Import uses a
user-selected file; export downloads a Blob. Neither needs access
to arbitrary filesystem paths. Source strings remain configuration paths;
the browser does not open the audio or resolve their location. Media is decoded
locally through object URLs, with no upload, autoplay or soundtrack playback.
Replaced/reset files release their object URLs. **Reset media** retains settings;
**Reset example** restores both the project and the built-in image.

The exported JSON contains only `ProjectConfig` fields. Synthetic signal levels,
the media, video time, UI state and preview metadata are separate and never enter the config.
An imported valid project retains its values, names and source paths; missing
fields acquire Python defaults. Values beyond a slider's suggested range extend
that slider instead of being silently truncated. Number inputs allow finer tuning.
Removing a signal also removes effects that refer to it; renaming updates them.

## Preparation JSON import

The analysis preparation manifest (`analysis/<key>.json` in the cache, with its path
printed by `analyze`) now includes a top-level `config` containing
the full `ProjectConfig`, including effects and visualizer styles. Dropping it extracts
and validates that config; cache references and analysis metadata are not exported.
`analyze` rewrites it even on cache hits, so it records the latest supplied settings.
The config sits outside cache-key parameters: style edits still reuse audio analysis.

Old analysis manifests without `config` cannot reconstruct the full project. Rerun
`analyze` with this version and the original config, or drop that config directly.
The editor does not read referenced NPZ files or cached audio from a manifest;
waveform/spectrum data and reactive levels remain simulated.

Invalid JSON, failed media decoding and ambiguous batches leave the current project
and media intact. A newer drop cancels pending media decoding. Config JSON is limited
to 1 MiB; media is limited to 32 megapixels and 16,384 pixels per edge. Browser codec
support determines accepted videos; try H.264 MP4 or WebM if decoding fails. Image
files use the browser-decoded still, including for animated formats.

## Source of truth and build

`src/beatbloom/config.py` remains authoritative. `tools/build_editor.py` exports:

- `ProjectConfig.model_json_schema()`: fields, types, enums, required fields and bounds;
- model instances: defaults, including Pydantic `default_factory` values;
- model-specific available stems, FFT size choices and Python whitespace semantics;
- shared bloom/luminance constants and the Python version;
- an initial valid project with effects and two visualizers.

The schema hash fingerprints the embedded contract. It is not a schema migration
or a security signature. The entire generated file is deterministic and checked
byte-for-byte by CI. Changes to Python defaults, constants, schema or editor sources
require regeneration:

```bash
make editor
make editor-test
make check
```

No npm installation is required to build or use this prototype. The build is a
small Python assembler; the sources are plain JavaScript and Canvas. Node 22+
is needed only for cross-language tests. If the interface grows, migrate source
code to TypeScript and bundle it to one classic script (IIFE). The deliverable
should still contain no imports, external scripts or runtime build dependencies.
Do not load separate ES modules from `file://`: local module security varies
and can prevent a no-server workflow.

## Contract and validation limits

JSON Schema does **not** describe every Pydantic `model_validator`, such as
signal references, source/stem exclusion, region sums and power-of-two FFT sizes.
`core.js` supplements generated field checks with these semantic rules. They
are deliberately small, explicit and tested against Python-labeled fixtures in
`tools/editor_cases.py`. This is still a maintenance obligation: every new Python
cross-field rule requires a corresponding browser rule and valid/invalid fixtures.
CI also passes every accepted fixture's exported JSON back through strict Pydantic.

JSON numbers in JavaScript do not preserve lexical distinctions such as `4096.0`
versus `4096`. Integers are exported canonically as integers. This editor supports
the subset of JSON Schema emitted by today's models, not arbitrary JSON Schema.
Extending the model with new schema keywords requires extending its validator.
Python `beatbloom validate` remains the final configuration authority and checks
the actual exported file; neither validator verifies that media paths exist.

Browser fields are generated from schema types and bounds. English labels,
suggested slider maxima and grouping are UI concerns. These suggestions never
replace validation bounds. Unbounded effect amounts remain unbounded in JSON.
An invalid draft disables export and preserves the last valid preview.

## Preview scope

| Setting | Fixed preview behavior |
| --- | --- |
| Layout, region, colors, opacity, gaps, line width, fill | Applied to synthetic overlays |
| Waveform window, points, playhead | Applied to a deterministic synthetic shape |
| Spectrum band count | Changes the number of synthetic bars |
| Effect mappings, amounts, brightness range | Mixed using simulated normalized levels |
| Brightness, exposure, saturation, zoom | Illustrative Canvas rendering |
| Bloom | Approximate Canvas blur/compositing, not OpenCV pixel equivalence |
| Frequencies, FFT, percentiles, envelopes, gate, gamma | Exported; no music analysis here |
| Demucs model/device/options | Exported; no separation in the browser |
| Selected image/video still, native size, video time | Local preview only; not exported |
| Soundtrack, CLI grading | Outside `ProjectConfig` and outside this prototype |

Effects are applied before visualizers, matching Python's layer order. Overlay
geometry and line widths use the media's native canvas size. Effect processing uses
an intermediate bitmap with at most 1,280 pixels on its longest edge for responsiveness,
then scales back to native size. A still can explain geometry and artistic intensity;
it cannot establish how actual music will react. Canvas antialiasing, zoom sampling
and bloom differ from OpenCV.
This preparation does not port librosa, SciPy, Demucs or FFmpeg into the browser.

## Verification

`make editor-test` verifies configuration examples, invalid cross-field cases,
source path preservation, unusual dictionary names, strict Python export validity
and effect mixing parity. Media tests exercise decoder-event lifecycle, native
metadata, paused seeking, replacement, cancellation, failure and URL cleanup with
in-memory mocks. No browser or server is started by these tests.

An optional real-browser check opens the artifact with `file://`, verifies zero
HTTP requests, edits sliders and tracks, rejects invalid drafts, drops a portrait PNG,
seeks a generated WebM still, restores a preparation config and validates downloaded
exports in Python. FFmpeg with the VP9 encoder is needed for the generated video:

```bash
# Development/test dependencies only, not part of the user's HTML:
npm install --no-save --package-lock=false playwright
npx playwright install chromium
node tests/editor_browser.cjs
```

`BEATBLOOM_BROWSER_EXECUTABLE` can select an installed Chromium. `NODE_PATH`
may select a separately installed Playwright package. No web server is involved.

When a browser cannot start, `tests/editor_dom.cjs` offers a complementary check:

```bash
npm install --no-save --package-lock=false jsdom@26.1.0 @napi-rs/canvas
node tests/editor_dom.cjs
```

It executes the real embedded scripts with a DOM and native Canvas, checks form
changes, media/config drops, native dimensions and import/export behavior, and
validates the exported JSON in Python. PNG decoding is native; video decoder events
are mocked. It does not test browser codecs, security policies, CSS layout or
browser compatibility.

## Next phase: real snapshots without a server

Add a separate Python command that generates an offline preview package containing
a chosen video frame, absolute timestamp, normalized signal levels and the cached
waveform/spectrum series needed for display. Embed PNG data and JSON directly in
the HTML, or import one user-selected package. Package format and config schema
must have separate version numbers.

The browser can then redraw geometry and colors against real precomputed data
without recomputing audio. Styling changes remain instantaneous. A change to
analysis parameters marks the snapshot stale and asks for a fresh Python export;
it must not pretend to reproduce a new analysis using old data. Real signal data
belongs to the package, not the exported render configuration.

Keep numerical analysis and full video rendering in Python. Share configuration
and numerical fixtures, and use tolerant visual comparisons for overlapping
renderer behavior. A pixel-identical preview would require a common renderer or
Python/WASM and is a separate, significantly larger project.
