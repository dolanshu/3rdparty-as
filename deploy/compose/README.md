# `deploy/compose/` — M4b-8 dev HTTPS（同源）

在单机 Docker（含 WSL2）上拉起 **PostgreSQL 12.22**、**config-service** runtime 与 **Caddy** 自签 TLS 反代，使控制台静态资源与 `/internal/v1` API 共享同一 HTTPS origin。用于 [`docs/acceptance/m4b-8-runbook.md`](../../docs/acceptance/m4b-8-runbook.md) 与 `test-plan.md` §1.4 M4b-8；**不是**生产部署目标（生产见 `deploy/helm/`）。

## 前置

- Docker Engine + Compose v2
- `openssl`（生成自签证书）
- 可选：仓库根目录 `uv`（若要在宿主机直接连 `localhost:55432` 跑 migrate，而非 compose profile）

## 快速开始

```sh
cd deploy/compose
cp .env.example .env
# 编辑 .env：将 AS_AUDIT_RESOURCE_HMAC_KEY_B64 设为 32 字节 base64（openssl rand -base64 32）

./scripts/gen-certs.sh
docker compose up -d postgres
./scripts/migrate.sh
./scripts/bootstrap-admin.sh   # 交互式：首个 administrator
./scripts/up.sh
./scripts/smoke-https.sh
```

浏览器打开 `https://localhost:8443/`（接受自签证书警告）。登录须 HTTPS scheme；Caddy 向 config-service 转发 `X-Forwarded-Proto: https`，且 `AS_CONFIG_TRUSTED_PROXIES` 覆盖 compose 网络 `10.89.0.0/24`。

## 服务

| 服务 | 说明 |
|---|---|
| `postgres` | `postgres:12.22`，库 `as_config`；init 脚本创建 `as_config_owner` / `as_config_web` + `as_config_runtime`（NOLOGIN） |
| `config-service` | 镜像 `deploy/docker/config-service.Dockerfile`；仅 runtime DSN + HMAC key |
| `caddy` | 宿主机 `8443` → HTTPS → `config-service:8000` |
| `testbed-health` | 可选；`http://10.89.0.30:8080/health` 返回 `{"healthy":true}`，供 7.5 fleet probe 联调 |
| `migrate` / `bootstrap-admin` | `--profile setup` 一次性任务 |

## 脚本

| 脚本 | 作用 |
|---|---|
| `scripts/gen-certs.sh` | 写入 `certs/tls.crt` / `tls.key`（localhost SAN） |
| `scripts/migrate.sh` | `as-config-migrate`（owner DSN） |
| `scripts/bootstrap-admin.sh` | `as-config-bootstrap-admin`（交互） |
| `scripts/up.sh` | 构建并启动 runtime + 反代 + health stub |
| `scripts/smoke-https.sh` | `curl -k --noproxy '*'` 检查 `/` HTML 与未认证 session 401（避免宿主机 `HTTP(S)_PROXY` 对 localhost 返回 504） |
| `scripts/m4b-8-browser-evidence.sh` | Playwright 截图 + API 同源证据（需 `M4B8_E2E_PASSWORD`；Ubuntu 20.04 无本机浏览器时自动用 Playwright Docker 镜像） |

## 宿主机 integration 测试（M5）

`pytest -m integration` 默认 DSN 为 `postgres:secret@127.0.0.1:55432`；compose 超级用户密码见 `.env.example`（默认 `postgres`）。在 compose Postgres 已启动时：

```sh
# 仓库根目录
make test-integration-compose
# 等价于 AS_PG_TEST_DSN=postgresql://postgres:postgres@127.0.0.1:55432/as_config pytest -m integration
```

## 宿主机 migrate（可选）

Postgres 映射端口默认 `55432`：

```sh
AS_CONFIG_OWNER_DSN="postgresql://as_config_owner:as_config_owner_dev@127.0.0.1:55432/as_config" \
  AS_CONFIG_RUNTIME_ROLE=as_config_runtime \
  uv run --directory services/config-service as-config-migrate
```

## 限制

- 密码与 HMAC 为 **开发占位**，不得用于生产。
- 不实现 7.2d 生产 ingress-nginx preflight；M4b-8 浏览器证据见 runbook 中的 **BLOCKED** 项。
- 销毁数据：`docker compose down -v`
