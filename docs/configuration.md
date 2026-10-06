# Configuration reference (schema v2)

```json
{
  "schema_version": 2,
  "separation": {"model": "htdemucs_6s", "device": "auto"},
  "signals": {
    "kick": {
      "stem": "drums",
      "low": 40,
      "high": 120,
      "feature": "rms",
      "attack_ms": 15,
      "release_ms": 200,
      "gate": 0.3,
      "gamma": 1.5
    },
    "energy": {"stem": "mix", "feature": "loudness"}
  },
  "effects": [
    {"signal": "kick", "effect": "zoom", "amount": 0.006},
    {"signal": "energy", "effect": "brightness", "range": [0.6, 1.05]}
  ]
}
```

`schema_version` is required and must be `2`. `signals` is a nonempty object
whose keys are nonblank names. `effects` defaults to an empty list, allowing
analysis without visual mappings. JSON keys are case-sensitive; unknown keys
and numeric strings are rejected. Numbers must be finite.

## Signals

| Field | Default | Meaning / accepted values |
| --- | --- | --- |
| `stem` | Absent | `mix`, `drums`, `bass`, `vocals`, `other`, `guitar`, `piano` |
| `source` | `--drive`, then original audio | Audio path, relative to the JSON file; mutually exclusive with `stem` |
| `low` | 0 Hz | Lower cutoff, 0 ≤ value < 22050 |
| `high` | 22050 Hz | Upper cutoff, 0 < value ≤ 22050; greater than `low` |
| `feature` | `onset` | `onset`, `rms`, `loudness` |
| `attack_ms` | 10 | Rising time constant, ≥ 0; 0 disables rising smoothing |
| `release_ms` | 400 | Falling time constant, ≥ 0; 0 disables falling smoothing |
| `gate` | 0 | Subtract threshold and rescale, 0 ≤ value < 1 |
| `gamma` | 1 | Exponent after gating, > 0 |
| `ref_percentile` | 99.5; 99 for loudness | Reference percentile, 0 < value ≤ 100 |
| `floor_percentile` | 5 | Loudness dB floor percentile, 0 ≤ value < reference |

Omitting `stem` and `source` uses `--drive` when provided, otherwise the mix.
`stem: "mix"` explicitly selects the original audio, regardless of `--drive`.
Other stem names invoke Demucs only when a separation cache is missing.
`source` uses an existing audio file without invoking separation.

Analysis decodes mono PCM at 44100 Hz, extracts features every 256 samples
with a 2048-sample frame and keeps absolute float64 timestamps. Frequency
isolation uses fourth-order forward/backward Butterworth filters. Only `high`
gives a low-pass filter; only `low` gives a high-pass filter.

- `onset`: Librosa spectral onset strength, useful for attacks.
- `rms`: root mean square amplitude, useful for sustained energy.
- `loudness`: RMS in dB, normalized between percentiles; this is the
  prototype's naming and does not measure LUFS.

Full-track features are normalized, gated, raised to `gamma`, then smoothed
at the native audio feature rate. The renderer interpolates these envelopes
at each frame timestamp. Silence produces zero; a source contributes zero
before time zero and after it ends. External source files must already align
with the mix at time zero. Offsets are not supported in v0.2.

## Effects

Each mapping contains `signal` and `effect`. The named signal must exist.
One signal may drive multiple effects; multiple signals may drive one effect.

| `effect` | Required setting | Interpretation |
| --- | --- | --- |
| `bloom` | Nonnegative `amount` | Add blurred highlights above luminance 0.55 |
| `exposure` | Nonnegative `amount` | Multiply intensity by `1 + amount × envelope` |
| `saturation` | Nonnegative `amount` | Multiply chroma by `1 + amount × envelope` |
| `zoom` | Nonnegative `amount` | Scale around frame center by `1 + amount × envelope` |
| `brightness` | `range: [dark, bright]` | Two nonnegative factors; interpolate by envelope |

Brightness requires `range` and forbids `amount`. Other effects require
`amount` and forbid `range`. Additive amounts sum before effects are applied;
brightness factors multiply. A zero envelope still applies the `dark` factor,
including silence and a finished source. Reversed brightness ranges are valid
for an inverse response.

Order: zoom → brightness → exposure → saturation → bloom, then clip to 0..1.
Exposure is an intensity factor, not photographic stops. Bloom sigma is
18 pixels. `--grade` applies FFmpeg filters afterwards.

## Separation

The optional `separation` object controls Demucs and the identity of cached stems.
It is not used for mix-only or external-file configurations.

| Field | Default | Meaning / accepted values |
| --- | --- | --- |
| `backend` | `demucs` | Only Demucs is supported in v0.2 |
| `model` | `htdemucs_6s` | Six stems; `htdemucs` has drums, bass, vocals, other |
| `device` | `auto` | `auto`, `cpu`, `cuda`, `cuda:N`, `mps`; auto chooses CUDA or CPU |
| `shifts` | 1 | Random time shifts, integer ≥ 0; 0 skips averaging |
| `overlap` | 0.25 | Segment overlap, 0 ≤ value < 1 |
| `segment` | Model default | Optional integer seconds, 1–7; reduce to lower memory use |
| `jobs` | 0 | CPU workers, integer ≥ 0 |
| `seed` | 0 | Random seed, integer 0–4294967295 |

Guitar and piano signals require `htdemucs_6s`. Separation produces all model
stems as stereo 44100 Hz float32 WAV files. All lengths match; no peak
normalization is applied per stem. Downloaded model weights use Demucs's own
cache; BeatBloom's `--cache-dir` controls the resulting stems and analysis.
CLI `--model` and `--device` override the JSON settings and are validated again.

## Caches and iteration

`separate` prepares all model stems; `analyze` prepares the configured signals.
`render` and `preview` fill missing stages automatically. `analyze` logs a JSON
manifest linking signal names to timestamped NPZ series and the stem manifest.
The NPZ files contain `timestamps` (float64), `values` (float32) and scalar
`duration` (seconds). Loading always disables pickle.

Cache identities use SHA256 of file contents and versioned processing settings.
Changing only effect mappings, grade, video, size, FPS or excerpt reuses signals.
Changing envelope settings reuses raw features. Changing source, frequency
cutoffs or extraction settings recomputes the relevant features. RMS and
loudness share raw RMS extraction but have different envelopes.

Each stage validates payload hashes and structure before reuse. Invalid entries
rebuild; process locks prevent duplicate simultaneous work. Entries are staged
before replacement, so a failed or interrupted producer preserves an old valid
entry. `--refresh` replaces the required entries after recomputing them.
Caches have no automatic size limit; remove their directory when needed.

## Updating a v0.1 configuration

Old `bands` files, including files without a version, are rejected. There is
no compatibility loader or automatic migration.

1. Set `schema_version` to `2`.
2. Replace the bands list with a `signals` object keyed by each former `name`.
3. Keep source, frequency and envelope parameters in each signal definition.
4. Move each effect weight to `{signal, effect, amount}` in the effects list.
5. Move brightness to `{signal, effect: "brightness", range: [dark, bright]}`.
6. Optionally replace manual Demucs source paths with `stem` aliases.

The repository examples already use v2. Run `beatbloom validate project.json`
to check a new file without loading media or downloading models. The generated
structural schema is [config.schema.json](config.schema.json); CLI validation
also checks cross-field ranges and references.

Native-rate smoothing may change the appearance slightly from v0.1's
frame-rate-dependent sampling. Tune attack/release on a preview; those changes
reuse the cached raw features.
