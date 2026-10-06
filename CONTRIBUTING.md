# Contributing to BeatBloom

Bug reports, documentation fixes, presets and code contributions are welcome.
For larger features, open an issue to discuss the scope before implementing.

## Set up

Install Python 3.10–3.14, uv and FFmpeg/ffprobe, then:

```bash
git clone https://github.com/odoucet/beatbloom.git
cd beatbloom
make install
uv run pre-commit install
```

Use `make format` before `make check`. Without Make, use the corresponding
`uv run ruff`, `uv run mypy` and `uv run pytest` commands from the README.
Run `make build` when changing packaging.

## Code and tests

- Keep analysis, mapping and rendering separate. Avoid new extraction work
  inside the video frame loop.
- Preserve full-track normalization when adding excerpt or preview support.
- Validate public configuration changes and document compatibility.
- Use type hints and logging; return actionable `BeatBloomError` messages.
- Cover meaningful behavior with small synthetic tests. Do not commit
  copyrighted media, private paths, separated stems or model weights.
- Mark tests requiring FFmpeg with `@pytest.mark.integration`.

To run only fast unit tests: `uv run pytest -m 'not integration'`.
To run integration tests: `uv run pytest -m integration`.
To inspect coverage: `uv run pytest --cov=beatbloom --cov-report=term-missing`.

Update dependencies in `pyproject.toml`, run `make lock`, then commit `uv.lock`.
Check with `uv sync --locked --all-extras --dev` to verify reproducibility.
Keep the generated schema in sync with `ProjectConfig.model_json_schema()`.

## Pull requests and releases

Describe the user-visible change and how it was verified. Add an entry under
`Unreleased` in the changelog. Small, focused PRs are easier to review.

Before a release, update `__version__` in `src/beatbloom/__init__.py`, update the
changelog date, run `make check` and `make build`, and test installation of the
wheel in a clean environment. Publishing a GitHub release or a PyPI package
is a separate maintainer action; CI does not publish automatically.

Contributions are provided under the project's MIT license.
