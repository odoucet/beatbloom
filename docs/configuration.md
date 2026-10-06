# Configuration reference (schema v1)

```json
{
  "schema_version": 1,
  "bands": [
    {
      "name": "kick",
      "low": 40,
      "high": 120,
      "feature": "rms",
      "attack_ms": 15,
      "release_ms": 200,
      "gate": 0.3,
      "gamma": 1.5,
      "effects": {"zoom": 0.006}
    }
  ]
}
```

`schema_version` defaults to `1` so existing `bands.json` files remain valid.
`bands` must contain at least one band, and names must be unique. JSON keys
are case-sensitive. Unknown keys and effects are rejected. Numeric values
must be finite JSON numbers, not numeric strings.

| Field | Default | Meaning / accepted values |
| --- | --- | --- |
| `name` | Required | Unique, nonblank signal name |
| `source` | `--drive`, then `--audio` | Audio file; a relative path is resolved against the JSON file's directory |
| `low` | 0 Hz | Lower cutoff, 0 ≤ `low` < 22050 |
| `high` | 22050 Hz | Upper cutoff, 0 < `high` ≤ 22050; strictly greater than `low` |
| `feature` | `onset` | `onset`, `rms` or `loudness` |
| `attack_ms` | 10 | Rising envelope time constant, ≥ 0 |
| `release_ms` | 400 | Falling envelope time constant, ≥ 0 |
| `gate` | 0 | Subtract this threshold and rescale, 0 ≤ `gate` < 1 |
| `gamma` | 1 | Exponent after gating, > 0 |
| `ref_percentile` | 99.5; 99 for `loudness` | Reference percentile, 0 < value ≤ 100 |
| `floor_percentile` | 5 | dB floor for `loudness`, 0 ≤ value < reference percentile |
| `effects` | `{}` | Nonnegative additive weights for `bloom`, `exposure`, `saturation`, `zoom` |
| `brightness` | Absent | Two nonnegative factors `[dark, bright]`, interpolated by the envelope |

Analysis uses mono PCM at 44100 Hz. Band filters are fourth-order Butterworth
filters applied forward and backward. Omit both cutoffs for the full spectrum.
Only `high` gives a low-pass filter; only `low` gives a high-pass filter.

## Features and processing order

- `onset`: Librosa's spectral onset strength; useful for attacks.
- `rms`: root mean square amplitude; useful for sustained energy.
- `loudness`: RMS expressed in dB and normalized between two percentiles.
  This retains the prototype's naming; it does **not** measure LUFS or apply
  EBU R128 perceptual weighting.

Each complete source track is decoded once per run. Features are sampled at
the output video frame rate, normalized on the complete source, gated, raised
to `gamma`, then smoothed using attack/release. Silence produces a zero
envelope. A source contributes zero after its audio ends.

Source tracks must already be aligned to the original mix at time zero;
independent stem offsets are not supported in v0.1. Paths may contain spaces
and Unicode. Configuration validation does not check file existence;
rendering checks all files before analysis.

## Mapping

For an envelope `e` in 0..1, `effects.zoom = 0.006` adds `0.006 * e` to the
zoom amount. The applied scale is `1 + zoom`. Effect weights add across bands.
Brightness is `dark + (bright - dark) * e`, and multiple brightness bands
multiply. A brightness band with a zero envelope still applies its `dark`
factor, including during silence and after its source ends.

Effects apply in this order: zoom → brightness → exposure → saturation → bloom.
Exposure and saturation multiply their respective quantity by `1 + amount`;
exposure is an intensity factor, not a number of photographic stops. Bloom
adds a blurred highlight layer above luminance 0.55 with sigma 18 pixels.
Frames are clipped to 0..1 after reactive effects. `--grade` applies FFmpeg
filters afterwards at encoding time.

## Migration from audioreact.py

Change the command prefix from `python audioreact.py` to `beatbloom render`.
The original bands and effect settings are accepted. If the JSON file was
moved into another directory, adjust its relative `source` paths accordingly.
Add `--overwrite` if replacing an existing output. `--preset` is now selectable;
its default remains `slow`, and `--crf` still defaults to 16.

Compared with the prototype, v0.1 fixes silent-track normalization, sub-frame
excerpt timing, exact fractional frame rates, tiny-frame bloom, encoder error
handling, incomplete-frame detection and accidental input overwrites. Frequency
limits are validated instead of silently clipping invalid high cutoffs.
