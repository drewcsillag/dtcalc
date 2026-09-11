.PHONY: check fmt lint types test install clean

check: lint types test

lint:
	uv run ruff check
	uv run ruff format --check

types:
	uv run mypy

test:
	uv run pytest

fmt:
	uv run ruff format
	uv run ruff check --fix

install:
	uv tool install --force .

clean:
	rm -rf .mypy_cache .pytest_cache .ruff_cache dist build
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
