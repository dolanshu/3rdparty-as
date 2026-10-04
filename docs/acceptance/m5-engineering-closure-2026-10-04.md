# M5 engineering closure evidence (2026-10-04)

Authoritative checklists: [`plan.md`](../plan.md) **§4.5**（2026-10-04 原关门）与 **§4.6**（D12 / ADR-0026 补交付；**不是 M2**）。

## Images (M5-1a)

| Image | ID |
|-------|-----|
| `as-platform:m5` | `sha256:be05fffd0705eeba5f5ff47d2c9fa9d3dc45d057743389b2da7d0410612ac317` |
| `as-config-service:m5` | `sha256:dc7b201ded3a494c7e6c33382a87d7f16794f5ce66000fed5054dedaaf9a45be` |

## kind cluster `as-m5` (M5-1b / M5-3)

- Helm release `as` in namespace `as-m5`: Deployments `translation`, `anti-fraud` **Running** with HTTP probes on `:8080`.
- **Rollout restart** `as-3rdparty-as-anti-fraud`: success (`deploy/kind/m5-rollout-scale.sh`).
- **Scale** anti-fraud deployment to 1 replica: success.
- In-pod: `GET http://127.0.0.1:8080/metrics` → `as_active_calls{pod="...",use_case="translation"} 0.0`.

## 7.2d ingress (M5-1c) — 关门 2026-10-04

- Ingress `as-3rdparty-as-config-service`: `nginx.ingress.kubernetes.io/ssl-redirect` / `force-ssl-redirect`, host `console.m5.test`, TLS `console-tls`, `trustedProxies` 非 `*`.
- **关门证据**：`make m5-7.2d-evidence`（`M5_7_2D_E2E_PASSWORD`）→ `artifacts/m5/<date>/7.2d-evidence.log`、浏览器 `7.2d-browser-log.json`；HTTP **308**、HTTPS **200**、Playwright HTTPS 登录。
- Runbook: [`m5-7.2d-ingress-runbook.md`](m5-7.2d-ingress-runbook.md).

## Runtime (M5-2)

- `AS_HEALTH_PORT` + `/health/ready` (503 when draining), `/metrics` Prometheus text.
- `AS_DOWNSCALE_GUARD_*` read at startup (`downscale_config.py`).
- Downscale runbook: [`m5-downscale-runbook.md`](m5-downscale-runbook.md).

## Reproduce

```sh
make gate && make chart-check && make test-integration-compose
make m5-cluster-evidence   # docker + kind; optional local copy under artifacts/m5/
```

## M5-1d — PostgreSQL for config-service Ready（历史 + 现行）

| 时点 | 做法 | 里程碑 |
|------|------|--------|
| **§4.5 关门时** | Chart 不内建 PG；kind 用 **compose 宿主机 `:55432`** + 网关 DSN（`m5-lib.sh`） | M5-1d |
| **M5 验收复盘后** | [ADR-0026](architecture/adr/0026-in-cluster-state-stores-proposal.md) + Helm **`stateStores`**；kind 默认 `M5_BUNDLED_STATE=1` | **M5 §4.6 / D12**（非 M2） |

M2 只覆盖 **`RedisStateStore` 代码缝**；在 K8s 里 **装** PG/Redis 属于运维交付（M5）。

## Dependencies (not M5 blockers)

| Item | Notes | Track |
|------|--------|-------|
| **HPA / O1 thresholds** | M6 后填 `values.yaml` | **Deferred → M6** |
| **D3 Redis Sentinel** | M2/O5 | **Deferred → M2/O5** |
| **Product SIP call survival** | M7 | **Deferred → M7** |
| **config-service Ready** | Bundled PG + `as-config-migrate` + headless Service DSN；`make m5-kind-verify` HTTP 200 | **§4.6 / M5-1d** |
| **ingress-nginx admission webhook** | kind 可删 VWC 后重跑 `m5-ingress-evidence.sh` | [`m5-state-stores-runbook.md`](m5-state-stores-runbook.md) |
| **Corporate HTTP proxy** | Use `NO_PROXY` + port-forward / in-cluster curl | **`make m5-kind-verify`** |
| **Maintainer sign-off** | **Approved 2026-10-04**（chat 授权代签） | [`m5-closure-adjudication-2026-10-04.md`](../reviews/m5-closure-adjudication-2026-10-04.md) |

## §217①② + H10 (ISSU / scale-down, 2026-10-04)

- `bash deploy/kind/m5-issu-scale-evidence.sh` or `make m5-issu-scale-evidence`
- Log: `artifacts/m5/<date>/issu-scale-evidence.log` — simulated `AS_M5_SIMULATED_ACTIVE_CALLS=3`, readiness **503** on drain, `plan_scale_down` allow (anti-fraud 2→1) and block (translation with calls)

## §4.6 closure (D12 / ADR-0026, 2026-10-04)

- `make gate` (863 passed), `chart-check`, `test-integration-compose` (142 passed), `make m5-kind-verify` → **OK**
- Pods: `postgres-0`, `redis`, `translation`, `anti-fraud`, `config-service` **Running**; NetworkPolicy `as-3rdparty-as-state-ingress` present
- Runbook: [`m5-state-stores-runbook.md`](m5-state-stores-runbook.md)

## Maintainer sign-off

| Field | Value |
|-------|--------|
| Date | 2026-10-04 |
| Scope | M5 engineering closure (kind); reviews + adjudication complete |
| Not claimed | REQ / `test-plan` acceptance; M6 HPA/O1; M7 product SIP |
| Record | [`m5-closure-adjudication-2026-10-04.md`](../reviews/m5-closure-adjudication-2026-10-04.md) |
