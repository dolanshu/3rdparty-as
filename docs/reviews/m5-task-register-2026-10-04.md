# M5 任务登记与评审索引（2026-10-04）

> **Spec 来源**：[`plan.md`](../plan.md) §4.4（§217 关门条件）、§4.5、§4.6；[`m5-closure-adjudication-2026-10-04.md`](m5-closure-adjudication-2026-10-04.md) 逐项裁决。  
> **流程**：每项任务独立 review 文档 → 维护者级 adjudication（**Accept / Fix / Deny**）。**不等于** REQ 全绿或维护者签字。

## 阶段 0 — 基线（§4.4.4）

| Task ID | Plan 条目 | 证据 / 工件 | Review |
|---------|-----------|-------------|--------|
| M5-0a | `make gate` 全绿 | 本地 gate；plan §4.4.4 | [m5-0a-gate-review-2026-10-04.md](m5-0a-gate-review-2026-10-04.md) |
| M5-0b | `test-integration-compose` | `make test-integration-compose` | [m5-0b-integration-compose-review-2026-10-04.md](m5-0b-integration-compose-review-2026-10-04.md) |
| M5-0c | `chart-check` / CI | `deploy/helm/scripts/chart-check.sh` | [m5-0c-chart-check-review-2026-10-04.md](m5-0c-chart-check-review-2026-10-04.md) |

## 提前交付（§4.4.2）

| Task ID | Plan 条目 | Review |
|---------|-----------|--------|
| M5-a | Helm chart 骨架（ADR-0013） | [m5-a-helm-chart-review-2026-10-04.md](m5-a-helm-chart-review-2026-10-04.md)（与 [m5-helm-alerts-review.md](m5-helm-alerts-review.md) H1–H9 对齐） |
| M5-b | 告警规则（REQ-NF-14） | [m5-b-alerts-review-2026-10-04.md](m5-b-alerts-review-2026-10-04.md) |
| M5-c | `plan_scale_down`（ADR-0010） | [m5-c-downscale-guard-review-2026-10-04.md](m5-c-downscale-guard-review-2026-10-04.md) |
| M5-d | `as_active_calls` 契约（ADR-0005） | [m5-d-metrics-contract-review-2026-10-04.md](m5-d-metrics-contract-review-2026-10-04.md) |
| M5-e | PostgresVersionStore + integration | [m5-e-version-store-review-2026-10-04.md](m5-e-version-store-review-2026-10-04.md) |
| M5-f | 容器镜像 + SIGTERM draining smoke | [m5-f-container-draining-review-2026-10-04.md](m5-f-container-draining-review-2026-10-04.md) |

## 阶段 1 — 部署与 7.2d（§4.4.4 + M4b-7.2d）

| Task ID | Plan 条目 | Review |
|---------|-----------|--------|
| M5-1a | 镜像 `as-platform:m5` / `as-config-service:m5` | [m5-1a-images-review-2026-10-04.md](m5-1a-images-review-2026-10-04.md) |
| M5-1b | kind `as-m5` + Helm AS | [m5-1b-kind-helm-review-2026-10-04.md](m5-1b-kind-helm-review-2026-10-04.md) |
| M5-1c | Ingress 模板 / 对象 | [m5-1c-ingress-template-review-2026-10-04.md](m5-1c-ingress-template-review-2026-10-04.md) |
| M5-1d | config-service Ready + PG | [m5-1d-config-pg-review-2026-10-04.md](m5-1d-config-pg-review-2026-10-04.md) |
| M5-7.2d | §217③ runbook 1–6 + 浏览器 | [m5-7.2d-ingress-closure-review-2026-10-04.md](m5-7.2d-ingress-closure-review-2026-10-04.md) |

## 阶段 2 — draining / 缩容（§4.4.4）

| Task ID | Plan 条目 | Review |
|---------|-----------|--------|
| M5-2a | `/metrics` `as_active_calls` | [m5-2a-metrics-runtime-review-2026-10-04.md](m5-2a-metrics-runtime-review-2026-10-04.md) |
| M5-2b | `/health/ready` 503 draining | [m5-2b-readiness-review-2026-10-04.md](m5-2b-readiness-review-2026-10-04.md) |
| M5-2c | `AS_DOWNSCALE_GUARD_*` 读取 | [m5-2c-downscale-config-review-2026-10-04.md](m5-2c-downscale-config-review-2026-10-04.md) |
| M5-2d | downscale runbook | [m5-2d-downscale-runbook-review-2026-10-04.md](m5-2d-downscale-runbook-review-2026-10-04.md) |

## 阶段 3 — 关门证据 + §217①②（§4.4.4 / §217）

| Task ID | Plan 条目 | Review |
|---------|-----------|--------|
| M5-3a | rollout restart | [m5-3a-rollout-review-2026-10-04.md](m5-3a-rollout-review-2026-10-04.md) |
| M5-3b | scale + `plan_scale_down` | [m5-3b-scale-guard-review-2026-10-04.md](m5-3b-scale-guard-review-2026-10-04.md) |
| M5-217 | §217①② ISSU + 模拟 `active_calls` | [m5-217-issu-scale-review-2026-10-04.md](m5-217-issu-scale-review-2026-10-04.md) |
| M5-H10 | 运维接线（metrics → plan） | [m5-h10-ops-wiring-review-2026-10-04.md](m5-h10-ops-wiring-review-2026-10-04.md) |
| M5-3c | §4.5 文档 + helm 评审注记 | [m5-3c-closure-docs-review-2026-10-04.md](m5-3c-closure-docs-review-2026-10-04.md) |

## §4.6 D12 / ADR-0026

| Task ID | Plan §4.6 checklist | Review |
|---------|---------------------|--------|
| M5-D12-adr | ADR-0026 accepted | [m5-d12-adr-0026-review-2026-10-04.md](m5-d12-adr-0026-review-2026-10-04.md) |
| M5-D12-helm | `stateStores` 模板 + chart-check | [m5-d12-helm-state-review-2026-10-04.md](m5-d12-helm-state-review-2026-10-04.md) |
| M5-D12-kind | `M5_BUNDLED_STATE` kind | [m5-d12-kind-bundled-review-2026-10-04.md](m5-d12-kind-bundled-review-2026-10-04.md) |
| M5-D12-prod | on-prem + migrate Job + HA runbook | [m5-d12-production-profile-review-2026-10-04.md](m5-d12-production-profile-review-2026-10-04.md) |

## 明确不在本登记（§4.4.3 后置）

HPA 阈值、容量告警（H12）、D3 Sentinel、M7 真 SIP 不掉呼叫 — **Deny 纳入 M5 签字范围**（见 adjudication）。
