.DEFAULT_GOAL := help
.PHONY: help install install-demucs lint format typecheck test check build lock clean editor editor-check editor-test

help:
	@echo "install    Sync development dependencies and optional plots"
	@echo "install-demucs  Also install optional Demucs/PyTorch"
	@echo "format     Format Python and apply safe Ruff fixes"
	@echo "check      Run lint, strict typing and all tests"
	@echo "test       Run unit and FFmpeg integration tests"
	@echo "build      Build wheel and source distribution"
	@echo "editor     Generate the standalone offline HTML editor"
	@echo "editor-check  Check generated HTML is up to date"
	@echo "editor-test   Run Python/JavaScript contract tests (Node 22+)"
	@echo "lock       Update uv.lock after dependency changes"
	@echo "clean      Remove generated caches and build outputs"

install:
	uv sync --locked --extra plot --dev

install-demucs:
	uv sync --locked --extra plot --extra demucs --dev

format:
	uv run ruff check --fix .
	uv run ruff format .

lint:
	uv run ruff format --check .
	uv run ruff check .

typecheck:
	uv run mypy

test:
	uv run pytest

check: lint typecheck test

build:
	uv build

editor:
	uv run --locked python tools/build_editor.py

editor-check:
	uv run --locked python tools/build_editor.py --check

editor-test: editor-check
	node --test tests/editor_contract.test.cjs tests/editor_media.test.cjs

lock:
	uv lock

clean:
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
