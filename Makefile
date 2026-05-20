.PHONY: help install lint fmt typecheck test cov check perf demo clean
PATH_ARG ?= .
ARGS ?=

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "%-12s %s\n", $$1, $$2}'

install: ## Sync runtime + dev deps
	uv sync --extra dev

lint: ## ruff check + format check
	uv run ruff check src tests
	uv run ruff format --check src tests

fmt: ## Auto-fix lint and format
	uv run ruff check --fix src tests
	uv run ruff format src tests

typecheck: ## mypy on src
	uv run mypy src

test: ## pytest (excludes perf marks)
	uv run pytest

cov: ## pytest with coverage thresholds
	uv run pytest --cov=src/scout --cov-branch \
	  --cov-fail-under=85 \
	  --cov-report=term-missing

check: lint typecheck cov ## Everything CI runs, locally

perf: ## Perf smoke (excluded from CI default)
	uv run pytest -m perf

demo: ## Scan a path: make demo PATH_ARG=/path ARGS="--strict"
	uv run scout $(PATH_ARG) $(ARGS)

clean: ## Remove build artifacts and caches
	rm -rf .venv .ruff_cache .mypy_cache .pytest_cache dist build *.egg-info
	find . -name __pycache__ -prune -exec rm -rf {} +
