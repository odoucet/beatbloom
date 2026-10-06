.DEFAULT_GOAL := help
.PHONY: help install lint format typecheck test check build lock clean

help:
	@echo "install    Sync development dependencies and optional plots"
	@echo "format     Format Python and apply safe Ruff fixes"
	@echo "check      Run lint, strict typing and all tests"
	@echo "test       Run unit and FFmpeg integration tests"
	@echo "build      Build wheel and source distribution"
	@echo "lock       Update uv.lock after dependency changes"
	@echo "clean      Remove generated caches and build outputs"

install:
	uv sync --locked --all-extras --dev

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

lock:
	uv lock

clean:
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
