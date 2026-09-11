.PHONY: check fmt lint types test coverage coverage-check install clean

check: lint types test

lint:
	uv run ruff check
	uv run ruff format --check

types:
	uv run mypy

test:
	uv run pytest

# COVERAGE_PROCESS_START plus the hook on PYTHONPATH is what lets coverage see
# the `python -m dtcalc` child that the interactive tests drive through a pty.
# Without it repl.py reads as barely tested when it is exercised end to end.
COVERAGE_ENV = COVERAGE_PROCESS_START=$(CURDIR)/pyproject.toml \
               PYTHONPATH=$(CURDIR)/tests/coverage_hook

coverage:
	rm -f .coverage .coverage.* coverage.json
	$(COVERAGE_ENV) uv run coverage run -m pytest -q
	uv run coverage combine
	uv run coverage report
	uv run coverage json -o coverage.json --quiet
	uv run python scripts/coverage_badge.py

coverage-check:
	rm -f .coverage .coverage.* coverage.json
	$(COVERAGE_ENV) uv run coverage run -m pytest -q
	uv run coverage combine
	uv run coverage report
	uv run coverage json -o coverage.json --quiet
	uv run python scripts/coverage_badge.py --check

fmt:
	uv run ruff format
	uv run ruff check --fix

install:
	uv tool install --force .

clean:
	rm -rf .mypy_cache .pytest_cache .ruff_cache dist build coverage.json
	rm -f .coverage .coverage.*
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
