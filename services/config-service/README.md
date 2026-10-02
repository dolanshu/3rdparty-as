# `services/config-service/` — 规则治理

只拥有三样东西，没有别的：

| 职责 | 说明 |
|---|---|
| **规则版本库** | PostgreSQL 里不可变版本；diff 与回滚 |
| **变更单状态机** | draft → validation → approval → staged distribution → effective |
| **分发** | 向 AS 实例灰度滚动，遇到不健康上报自动回滚 |

## 为什么不是 GitOps

不能要求运营商运维人员为了改一个号段去学 Git。自托管的 Git 服务器还会把规则变更的可用性，押在另一个
分布式系统的可用性之后 —— 对于一个必须在凌晨 03:00 改号网的网元来说不行。理由在
[`../../docs/architecture/新系统整体架构.md`](../../docs/architecture/新系统整体架构.md) §5.1，
记为 ADR-0006。

## 边界

版本库是**我们的**。审批可以通过 `ApprovalGate` 抽象委派给运营商的 OSS 或工单系统 —— 但规则可用性
绝不能完全依赖一个外部系统的可用性。

## Runtime

从仓库根目录运行 ASGI 服务：

```sh
uv run --directory services/config-service as-config-service
```

必须设置 `AS_CONFIG_DSN`、`AS_CONFIG_RUNTIME_ROLE` 和
`AS_AUDIT_RESOURCE_HMAC_KEY_B64`。最后一项必须是 base64 编码的 32 字节密钥；例如可由部署密钥管理系统
生成并注入。可选项为 `AS_CONFIG_SCHEMA`（默认 `as_config`）、`AS_AUDIT_SCHEMA`（默认
`console_audit`）、`AS_CONFIG_HOST`（默认 `127.0.0.1`）、`AS_CONFIG_PORT`（默认 `8000`）、
`AS_CONFIG_PROXY_HEADERS`（默认 `false`）及 `AS_CONFIG_TRUSTED_PROXIES`。启用 proxy headers 时，必须
显式设置后者为受信任代理 IP/CIDR 列表；不接受 `*`。

数据库角色必须先由 DBA 独立预配置：可登录连接角色须能 `SET ROLE` 到专用
`NOLOGIN` 的 `AS_CONFIG_RUNTIME_ROLE`；runtime role 不得拥有 `SUPERUSER`、`CREATEROLE` 或任何角色成员资格。
`as-config-migrate` 是手动 owner-only 设置步骤，必须在 bootstrap 与启动 web Pod 前运行。它使用
`AS_CONFIG_OWNER_DSN`，只创建/验证专用 schema、调用各 store 的 `ensure_schema()`，并配置精确的 runtime
grants；它不创建或修改数据库角色，也不切换角色：

```sh
AS_CONFIG_OWNER_DSN='<owner/setup connection string>' \
	AS_CONFIG_RUNTIME_ROLE='as_config_runtime' \
	uv run --directory services/config-service as-config-migrate
```

`AS_CONFIG_SCHEMA` 默认为 `as_config`，`AS_AUDIT_SCHEMA` 默认为 `console_audit`；两者必须是不同的非
`public` schema。迁移只授予运行角色 config schema 的 `USAGE` 和所需的表/列权限，不授予 runtime
`CREATE`、`DELETE` 或 `TRUNCATE`。Audit schema 的权限完全由
`PostgresAuditStore.ensure_schema()` 管理。

After migration, `as-config-bootstrap-admin` is a separate manual, one-time operation that creates the first
administrator in `AS_CONFIG_SCHEMA`. It also uses `AS_CONFIG_OWNER_DSN`:

```sh
AS_CONFIG_OWNER_DSN='<owner/setup connection string>' AS_CONFIG_SCHEMA='as_config' \
	uv run --directory services/config-service as-config-bootstrap-admin
```

The web Pod receives only `AS_CONFIG_DSN`, the runtime login credentials, and the audit HMAC key. Never put
`AS_CONFIG_OWNER_DSN` in Helm values, a runtime Secret, or the web Pod. Runtime startup only connects, runs
`SET ROLE`, and validates the grants; it performs no DDL, migrations, or role provisioning.

Console 与 `/internal/v1` API 必须由同一 HTTPS origin 对外提供。登录只接受 HTTPS scheme；反向代理必须保留可信的
scheme 信息。默认不信任 proxy headers；只有在部署时明确配置实际代理 IP/CIDR 后才启用。当前代码提供 ASGI factory/CLI，
但尚无生产 ingress、TLS 终止或 trusted-proxy 行为的部署证据，不能据此声称 HTTPS 部署已验证。

## 与 AS 实例的契约

一个 AS 实例上报**它当前加载的规则版本**。那个上报正是滚动升级安全的原因：ISSU 期间两个版本共存，
所以规则 schema 必须双向兼容（风险 R4、ADR-0009）。

## 未来依赖

| 依赖 | 用途 |
|---|---|
| platform（通过 seam 接口） | 工作区成员，仅引用 `StateStore` 等 seam 抽象，不反向 import |
| PostgreSQL | 规则版本库（不可变行 + 版本指针）与变更单状态机（draft → approval → staged → effective） |
| Redis | 分布式锁（变更单审批期间防并发冲突）、变更灰度分发的分布式协调 |
| OTel SDK | 观测性：指标、日志、trace 统一接入 |
| FastAPI 或等效轻量框架 | 对外暴露内部 API（规则版本查询、变更单 CRUD、灰度状态上报） |

## 状态

骨架。
