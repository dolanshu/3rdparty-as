# `platform/` — 内核（layer ②）

每个 AS 实例都构建于其上的共享壳。它包含对所有用例共同的东西，不含任何属于某一个用例的东西：

| 关注点 | 为什么住在这里 |
|---|---|
| 进程壳（`main`、`bootstrap`） | 启动、自检、关闭一个 AS 进程的统一方式 |
| B2BUA 状态机（`call_controller`） | 每个用例都需要的 RFC 3261 腿处理 |
| `decide()` seam | 用例注入其业务判决的唯一点 |
| `Transport` seam | 今天 UDP，生产里到 S-SBC 的 TLS（ADR-0016） |
| `StateStore` seam | 今天内存，生产里 Redis（ADR-0002） |
| 可观测性原语 | 每个进程统一的、基于 OTel 的信号模型 |

## 硬性规则

**这个包绝不能 import `apps/*`、`services/*` 或 `testbed/*`。**
依赖方向是单向的，由 `tests/test_library_independence.py` 断言，而非由目录布局保证。

## 状态

仅有骨架。代码通过 `docs/migration/triage.md` 里的甄别驱动迁移进来；绝不整块照搬。

## 进程壳环境变量（SIP / D10 工程）

| 变量 | 说明 |
|------|------|
| `AS_ENABLE_SIP_RUNTIME=1` | 启动 `SipStackService`（`ResipRuntimeListener` + 可选恢复） |
| `AS_SIP_ACCEPT_ALL_INVITES=1` | 测试 harness：原生 DUM 完成 100/180/200 并触发 dialog-established 回调 |
| `AS_RECOVERY_CASE` | Checkpoint `case` 命名空间（默认 `translation`） |
| `AS_RECOVERY_CALL_KEYS` | 逗号分隔的 call key；进程启动时经 `RecoveryCoordinator` 异步 restore |
| `AS_RECOVERY_NATIVE_ON_START` | 默认 `1`；为 `0` 时仅加载 checkpoint 到 `CallController` 而不起 RecoveryTU |
| `AS_REDIS_URL` | 可选；支持 `redis://` 与 `redis+sentinel://`；未配置 Redis 则 checkpoint 使用 `InMemoryStateStore`（开发） |
| `AS_REDIS_SENTINEL_HOSTS` | 可选；与 `AS_REDIS_SENTINEL_MASTER` 成对使用（逗号分隔 `host:port`） |
| `AS_REDIS_SENTINEL_MASTER` | Sentinel 服务名（master set name） |
| `AS_RECOVERY_CHECKPOINT_TTL_SECONDS` | Checkpoint TTL（默认 3600） |
| `AS_RESIP_RECOVERY_CHECKPOINT_FILE` | **仅测试**：单文件 adapter 回退路径 |
