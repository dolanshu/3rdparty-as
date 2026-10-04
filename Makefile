# 3rdparty-as — the local gate.
#
# `make gate` is the same set of checks CI layer ① runs, in the same order.
# Nothing is committed unless it is green here first (AGENT.md §Git rules).

.PHONY: help sync fmt lint type test test-unit test-integration test-integration-compose test-e2e test-perf chart-check gate

# Matches deploy/compose/.env.example POSTGRES_SUPERUSER_PASSWORD on published port 55432.
COMPOSE_PG_DSN ?= postgresql://postgres:postgres@127.0.0.1:55432/as_config

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

test-integration-compose: ## ② integration using deploy/compose Postgres (AS_PG_TEST_DSN)
	AS_PG_TEST_DSN="$(COMPOSE_PG_DSN)" uv run pytest -m integration -q

chart-check: ## helm lint + template guards (M5-0c; requires helm 3.x)
	deploy/helm/scripts/chart-check.sh

m5-cluster-evidence: ## kind cluster M5 rollout/ingress evidence (needs docker+kind)
	bash deploy/kind/m5-cluster-evidence.sh

m5-kind-verify: ## gate + chart-check + kind smoke (existing as-m5)
	bash deploy/kind/m5-verify.sh

m5-issu-scale-evidence: ## §217①② + H10 on existing kind-as-m5 (needs cluster)
	bash deploy/kind/m5-issu-scale-evidence.sh

m5-7.2d-evidence: ## 7.2d ingress L7 + browser HTTPS (needs M5_7_2D_E2E_PASSWORD)
	bash deploy/kind/m5-7.2d-evidence.sh

test-e2e: ## ③ end-to-end call flows
	uv run pytest -m e2e -q

test-perf: ## ④ capacity baseline (never part of the commit gate)
	uv run pytest -m performance -q

gate: lint type test-unit ## the pre-commit gate: lint, type, then layer ① (unit + contract)
