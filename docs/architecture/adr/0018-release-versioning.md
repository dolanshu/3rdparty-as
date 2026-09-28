# ADR-0018：统一产品 release 版本 + 组件接口独立版本

- **Status**: accepted
- **Date**: 2026-09-28
- **Decides**: §11.3 —— 一个产品 release 版本，独立的组件接口版本；杜绝 VERSION 漂移
- **回应 REQ**: REQ-NF-11

---

## Context（背景）

POC 阶段已经发生了 VERSION 漂移：根 `VERSION` 文件声明 `0.2.0`，但各组件自己的 `pyproject.toml` 都写着 `0.1.0`——两个数字两个家，没有任何自动化守卫阻止这个漂移。`AGENT.md` §8 明确把这件事列为 monorepo 要消灭的三大缺陷之一。

本产品的交付形态是**一客户一系统**。交付给运营商的是一个完整系统版本，不是一堆独立组件版本的组合。运营商收到的是一个 Docker 镜像集合 + Helm chart，版本号应该是一个单一的 release 号，而不是每个组件各报一个版本号让运维去对齐。

monorepo + uv workspace（ADR-0001）提供了统一版本治理的技术基础：所有组件在一个仓库，CI 可以在一次流水线中集中校验版本一致性，不需要跨仓脚本。

`AGENT.md` §8 已有明确规则草案：
- `./VERSION` 是产品 release 版本的**唯一源头**；
- `<member>/pyproject.toml` 携带该组件自己的接口版本；
- **任何成员都不得拥有 `VERSION` 文件**；
- `tests/test_version_consistency.py` 守卫 VERSION 是 SemVer 且 CHANGELOG 最新标题等于它。

## Decision（决策）

**根 `./VERSION` 文件** 是产品 release 版本的**唯一源头**。产品使用一个 release 版本号交付，每次发布 bump 根 VERSION 并同步更新 CHANGELOG 最新标题。

**每个组件**（`platform/`、`apps/*`、`services/*`）可在自己的 `pyproject.toml` 里声明**独立的接口版本**（语义化 SemVer），用于上游消费者引用。组件接口版本与产品 release 版本相互独立：接口 `0.3.1` 可以出现在产品 release `1.2.0` 中。

**任何组件都不得拥有独立的 `VERSION` 文件。** 根 VERSION 是唯一的 release 版本来源，组件只保留 `pyproject.toml` 中的接口版本。这两个版本的合法性和一致性由 `tests/test_version_consistency.py` 自动守卫。

版本治理的完整约束由 `AGENT.md` §8 定义；本 ADR 固化根 VERSION + pyproject 接口版本的二元结构，以及二者的守卫机制。

## Consequences（后果）

### Positive（正面）

- **消除 VERSION 漂移。** 根 VERSION 是 release 的唯一源头，自动化测试守卫它与 CHANGELOG、各组件 `pyproject.toml` 的 SemVer 合法性。POC 中 VERSION 与 pyproject 各报各数的情况不会再次发生。
- **交付版本号清晰可追溯。** 运营商运维收到的是一个 release 号（如 `as-product@1.0.0`），可以直接追溯到 Git tag、CHANGELOG 条目、Helm chart 版本，不需要自己对齐组件版本。
- **组件接口版本独立声明。** 跨组件边界的 API 变更（如 `platform` 给 `apps` 的接口从 `0.1.0` bump 到 `0.2.0`）有语义化标记，消费者可以显式 pin 或兼容性处理。

### Negative / accepted（负面 / 已接受）

- **版本治理稍复杂。** 同时维护根 VERSION + 各组件 pyproject 接口版本。但 `tests/test_version_consistency.py` 把手动维护负担消为零——CI 每次都自动跑 SemVer 合法性校验和 CHANGELOG 标题对齐检查，违反即阻塞 PR。
- **需要区分"release 版本"和"接口版本"两个概念。** 产品 release 号描述整个系统的交付版本，组件接口版本描述该组件对外暴露的 API 语义变更。在文档和沟通中需要明确这两个语义的区别。

## Alternatives considered（考虑过的备选）

| Option | Why not |
|---|---|
| 每个组件独立 VERSION 文件 | 漂移问题更严重。每个组件各有一个 VERSION 文件 + pyproject.toml version，一个数字变成两个数字的漂移问题。运营商收到的是一堆版本号的组合，不可追溯、不可对齐 |
| 只靠 pyproject.toml version | `pyproject.toml` 的 version 是 Python 包发布版本，不是产品 release 概念。两者语义不同：release 版本描述整个系统的交付快照，pyproject version 描述单个组件的接口语义。硬把 release 塞进 pyproject 会让版本语义混乱 |

## Evidence（证据）

- `tests/test_version_consistency.py` 已实现并通过，检查根 VERSION 与各组件 pyproject.toml 版本的 SemVer 合法性，以及 CHANGELOG 最新标题与根 VERSION 的对齐。
- `AGENT.md` §8 明确定义 VERSION 文件的唯一源头角色，以及"任何成员都不得拥有 VERSION 文件"的硬约束。
- ADR-0011 确立的 sippy 版本锁（commit pin + vendoring）与此版本治理理念一致：外部依赖走 commit pin + 自动化守卫，内部组件走根 VERSION + pyproject 接口版本的二元结构。

## Related（相关）

- [`../新系统整体架构.md`](../新系统整体架构.md) §11.3 开发模式 —— 版本治理节
- [`../../AGENT.md`](../../AGENT.md) §8 版本与依赖
- [`../../AGENT.md`](../../AGENT.md) §11 Git 规则（commit message 规范含 feat/fix 前缀，CHANGELOG 自动生成）
- [ADR-0011](0011-sip-stack-dual-path.md) 与 ADR-0019 外部依赖 pin 理念
