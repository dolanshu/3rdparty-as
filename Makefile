# 3rdparty-as — the local gate.
#
# `make gate` is the same set of checks CI layer ① runs, in the same order.
# Nothing is committed unless it is green here first (AGENT.md §Git rules).

.PHONY: help sync fmt lint type test test-unit test-integration test-e2e test-perf gate

help: ## list the targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-18s %s\n", $$1, $$2}'

sync: ## create or refresh the locked environment for the whole workspace
	uv sync

fmt: ## apply ruff format
	uv run ruff format .

lint: ## ruff format --check + ruff check
	uv run ruff format --check .
	uv run ruff check .

type: ## mypy, strict, src only
	uv run mypy

test: ## every layer below ④
	uv run pytest -m "unit or contract" -q
	uv run pytest -m integration -q
	uv run pytest -m e2e -q

test-unit: ## ① unit + contract
	uv run pytest -m "unit or contract" -q

test-integration: ## ② integration against simulated peers
	uv run pytest -m integration -q

test-e2e: ## ③ end-to-end call flows
	uv run pytest -m e2e -q

test-perf: ## ④ capacity baseline (never part of the commit gate)
	uv run pytest -m performance -q

gate: lint type test ## the pre-commit gate: lint, type, then all three layers
