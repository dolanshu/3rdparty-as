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
