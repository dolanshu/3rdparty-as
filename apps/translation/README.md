# `apps/translation/` — 号码翻译 AS

双腿 B2BUA。它终结来自 S-SBC 的 trunk INVITE（UAS），应用翻译与路由决策，再用一个新的 Call-ID
经 S-SBC 发起一个新的 INVITE 回去（UAC）。

**此处范围内：** 决策。声明式规则进，一个判决出。

**此处范围外：** SIP 机制（它们在 `platform/`）、会话状态（在 Redis）、规则存储与审批（在
`services/config-service/`）。

## 形态

| 关注点 | 在哪 |
|---|---|
| `decide()` 实现 | 本包，在内核的 seam 之上 |
| 翻译与路由规则 | 纯函数，无 socket、无时钟、做 TDD |
| 规则文档 | 由 config-service 交付，版本化，带兼容矩阵 |
| 会话状态 | 经 `StateStore` seam 进 Redis |

## 状态

骨架。决策模块是这里最先写的东西，且 test-first：它是全仓库价值最高的 TDD 目标。

判决模块已落地（2026-09-28）：`decision.py` 建立在内核 `decide()` 之上，纯函数、TDD；评审见 docs/reviews/m3-decision-modules-review.md。
