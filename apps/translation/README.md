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

## 产品 SIP runtime（工程 harness）

在仓库根目录，先构建 native runtime（`make m2-platform-resip-build`），再用**空规则集**启动 translation 进程壳 + UDP listener：

```bash
export AS_ENABLE_SIP_RUNTIME=1
export AS_USE_CASE=translation
# 可选：AS_HEALTH_PORT=8080  AS_REDIS_URL=redis://127.0.0.1:6379/0
uv run python -m as_platform
```

或使用本目录薄入口（同样设置 `AS_USE_CASE=translation`）：

```bash
export AS_ENABLE_SIP_RUNTIME=1
uv run python apps/translation/translation_sip_main.py
```

默认 `RuleSet(rules=())`：无匹配路由规则时入腿 INVITE 返回 **404**（S2 形状）。可通过 `AS_RULESET_JSON` 或 `AS_CONFIG_BUNDLE_PATH` 注入规则（见 `platform/src/as_platform/sip/README.md`）。这不等于 translation 业务规则已接线到 config-service 分发；也不等于 M7/M8 验收。
