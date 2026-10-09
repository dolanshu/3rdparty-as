# 3rdparty-as — the local gate.
#
# `make gate` is the same set of checks CI layer ① runs, in the same order.
# Nothing is committed unless it is green here first (AGENT.md §Git rules).

.PHONY: help sync fmt lint type test test-unit test-integration test-integration-compose test-e2e test-perf chart-check alert-check gate gate-strict \
	m2-native-restore m2-native-build m2-native-smoke m2-native-smoke-tcp m2-native-smoke-tls-runtime m2-native-smoke-tcp-runtime m2-native m2-platform-resip-build m7-platform-two-leg-build m7-platform-recovery-build m71-sim

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

alert-check: ## promtool check rules on deploy/alerts/as-alerts.yaml
	@command -v promtool >/dev/null 2>&1 || { echo "promtool not found; install prometheus or set PATH" >&2; exit 1; }
	promtool check rules deploy/alerts/as-alerts.yaml

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

m2-native-restore: ## M2 P0: extract bundled reSIProcate vendor source to repo cache
	bash testbed/simulators/resip-probe/scripts/m2-native.sh restore

m2-native-build: ## M2 P0: cmake-build reSIProcate + resip_probe under .cache/m2-resiprocate
	bash testbed/simulators/resip-probe/scripts/m2-native.sh build-resip
	bash testbed/simulators/resip-probe/scripts/m2-native.sh build-probe

m2-native-smoke: ## M2 P0: run resip_probe S1 UDP smoke from native cache build
	bash testbed/simulators/resip-probe/scripts/m2-native.sh smoke

m2-native-smoke-tcp: ## M2 P2b: run resip_probe S1 TCP smoke from native cache build
	bash testbed/simulators/resip-probe/scripts/m2-native.sh smoke-tcp

m2-native-smoke-tls-runtime: ## M2 P2d: platform TLS resip_runtime integration smoke (pytest)
	bash testbed/simulators/resip-probe/scripts/m2-native.sh smoke-tls-runtime

m2-native-smoke-tcp-runtime: ## M2 P2: product TCP resip_runtime integration smoke (pytest)
	bash testbed/simulators/resip-probe/scripts/m2-native.sh smoke-tcp-runtime

m2-native: m2-native-restore m2-native-build m2-native-smoke ## M2 P0: restore, build, and smoke native probe

m2-platform-resip-build: ## M2 P2c: cmake-build platform _resip_runtime extension
	bash testbed/simulators/resip-probe/scripts/m2-native.sh build-platform-resip

m7-platform-two-leg-build: ## M7 slice: cmake-build platform _resip_two_leg extension
	bash testbed/simulators/resip-probe/scripts/m2-native.sh build-platform-two-leg

m7-platform-recovery-build: ## M7 slice: cmake-build platform _resip_recovery extension
	bash testbed/simulators/resip-probe/scripts/m2-native.sh build-platform-recovery

m71-sim: ## M7.1 local SIP path, load scenarios, and chart policy text
	uv run pytest platform/tests/test_udp_retransmission_contract.py testbed/load/tests/test_scenarios.py testbed/load/tests/test_no_retransmit.py testbed/load/tests/test_harness.py testbed/simulators/tests -q

demo-story-a: ## pre-M8 demo story A (translation + control plane); see scripts/demo-review/README.md
	bash scripts/demo-review/story-a.sh

demo-story-b: ## pre-M8 demo story B (block 603 + anti-fraud decision)
	bash scripts/demo-review/story-b.sh

demo-story-c: ## pre-M8 demo story C (Helm / ops / alerts)
	bash scripts/demo-review/story-c.sh

demo-story-d: ## pre-M8 demo story D (checkpoint / Redis harness)
	bash scripts/demo-review/story-d.sh

demo-story-e: ## pre-M8 demo story E (capacity smoke + O1 report head)
	bash scripts/demo-review/story-e.sh

demo-review-all: ## run automated demo stories (best-effort; needs Redis for D)
	bash scripts/demo-review/run-all-automated.sh

gate: lint type test-unit ## the pre-commit gate: lint, type, then layer ① (unit + contract)

gate-strict: gate ## gate plus the REQ-G-3 ADR annotation scan (ADR-0015; also a blocking CI step in job ①)
	uv run python scripts/ci/check_adr_annotations.py
