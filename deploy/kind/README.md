# kind — M5 集群证据（开发/CI 可选）

在本地 Docker 上创建 [kind](https://kind.sigs.k8s.io/) 集群，加载 AS / config-service 镜像，安装 Helm chart，收集 **M5-3a/b** 与 **7.2d** 证据。

## 前置

- Docker
- `kind`, `kubectl`, `helm`（优先 `PATH`；否则仓库 `.tools/m71-bin`；或 `HELM_BIN`）
- 仓库根目录执行

**PostgreSQL（M5-1d）**：生产 Chart 默认 **不**内建 PG（`stateStores.enabled=false`）。**kind 默认** `M5_BUNDLED_STATE=1`（§4.6 / ADR-0026）：同 namespace `postgres-0` + `m5-config-migrate-kind.sh`。可选 `M5_BUNDLED_STATE=0` + compose 宿主机 `:55432`（`m5-lib.sh` 网关 DSN）。

## 一键证据

```sh
./deploy/kind/m5-cluster-evidence.sh
```

产物：`artifacts/m5/<UTC-date>/cluster-evidence.log`（及 ingress 检查摘要）。

## 验收（已有集群）

```sh
make m5-kind-verify   # gate + chart-check + Pod metrics + config-service port-forward
M5_STRICT=1 make m5-kind-verify   # 无 kind 集群或非 0 断言 → exit 1（M5.1-P1-1）
```

## 分步

| 脚本 | 作用 |
|------|------|
| `m5-kind-up.sh` | 创建集群 `as-m5`（若不存在） |
| `m5-images.sh` | `docker build` + `kind load` |
| `m5-helm-install.sh` | `helm upgrade --install`（AS 双用例，HPA 关） |
| `m5-ingress-evidence.sh` | **M5-1d** compose PG + **M5-1c** ingress-nginx + config-service Ingress + 集群内/ port-forward 检查 |
| `m5-rollout-scale.sh` | rollout restart + **§217①②/H10**（调用 `m5-issu-scale-evidence.sh`） |
| `m5-issu-scale-evidence.sh` | 模拟 `active_calls`、ISSU draining 503、`plan_scale_down` 允许/拒绝 |
| `m5-plan-scale-down-from-metrics.sh` | 从 Pod `/metrics` 拉取并执行 `plan_scale_down` |
| `m5-7.2d-evidence.sh` | **7.2d 关门**（`M5_7_2D_E2E_PASSWORD`）；`make m5-7.2d-evidence` |
| `m5-config-migrate-kind.sh` | bundled PG 上 `as-config-migrate` |
| `m5-verify.sh` | 本地门禁 + kind 冒烟（`make m5-kind-verify`） |
| `m5-gen-certs.sh` | kind 用 TLS（SAN 含 `console.m5.test` + localhost） |
| `m5-lib.sh` | compose PG、宿主网关 IP、runtime DSN（被其它脚本 source） |

## 公司 HTTP 代理

若 shell 设置了 `http_proxy`/`https_proxy`，**不要**用裸 `curl http://127.0.0.1` 验证 kind（请求会进公司代理 → 403/000）。证据脚本使用：

- 集群内 `curl` → `ingress-nginx-controller` Service；
- 或 `NO_PROXY=127.0.0.1,localhost` + `kubectl port-forward`。

## ingress-nginx admission webhook

`m5-ingress-evidence.sh` 会 `wait` admission-create Job；超时则打印 **WARN** 并记录 `admission_job_ok=0`（见 log）。生产不得静默删除 VWC；kind 开发若 Job 失败，在 runbook 中登记原因后再继续。

## 宿主机 80/443

默认 `m5-kind-up.sh` **未**映射 hostPort 80/443；宿主机直连 ingress 可能失败。验收以**集群内 curl** 或 **port-forward** 为准。若必须从宿主机测 80/443，需用带 `extraPortMappings` 的 kind 配置**重建**集群（单独变更，非 M5 默认）。
