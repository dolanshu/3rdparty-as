# ADR-0001/0002/0003/0018 M1 Draft Review Record

> 评审人：AI agent（grilling session）
> 日期：2026-09-28
> 范围：M1 阶段新写的 4 个 draft ADR
> 状态：**批量 draft review 通过，可转为 accepted**

## 评审方法

逐个对照：
1. ADR 注册表 README 的决策映射（§0 账本编号匹配）
2. 架构文档 §0 决策账本（决策内容一致性）
3. ADR-0019 的依赖关系（被 ADR-0019 引用的决策是否正确前置）
4. 每项 ADR 的 Context/Decision/Consequences 是否完整

---

## 1. ADR-0001：单 monorepo + uv workspace

- **Decides 账本**：决策 3 ✅
- **Context**：POC 三大硬伤（CI clone、Docker 上下文、版本漂移）描述准确
- **Decision**：uv workspace + AST 扫描守卫，与架构文档一致
- **Consequences**：正面 4 项、已接受 2 项，非空
- **证据**：test_workspace_layout.py / test_library_independence.py 存在且通过
- **评审结论**：✅ **通过**

## 2. ADR-0002：每用例一进程 + 状态外置 Redis

- **Decides 账本**：决策 2 ✅
- **Context**：POC sippy 阻塞模型 + InMemoryStateStore 重启丢会话
- **Decision**：进程无状态，状态全外置到 Redis（StateStore seam）
- **Consequences**：正面进程边界 = 故障域，已接受 Redis Sentinel 硬依赖
- **评审结论**：✅ **通过**

## 3. ADR-0003：单一 ISC 接入语义

- **Decides 账本**：决策 10 ✅
- **Context**：S-SBC 透明桥接 → AS 只需实现 ISC
- **Decision**：网外 AS 不实现双模适配，testbed 需 S-SBC 仿真器
- **Consequences**：正面只实现一种语义，已接受依赖运营商 S-SBC 正确桥接
- **评审结论**：✅ **通过**

## 4. ADR-0018：统一产品 release 版本 + 组件接口独立版本

- **Decides 账本**：§11.3 ✅（跨账本章节）
- **Context**：POC VERSION vs pyproject 漂移
- **Decision**：根 VERSION 是唯一 release 源头，组件声明接口版本
- **Consequences**：正面漂移消除，已接受版本治理稍复杂但 tests/test_version_consistency.py 守卫
- **评审结论**：✅ **通过**

---

## Adjudication

| ADR | 来源 | 问题摘要 | 裁决 | 状态 | 验证方式 |
|---|---|---|---|---|---|
| ADR-0001 | draft → accepted | 无问题，内容完整 | 接受 | 已关闭 | 对照注册表 §3 决策一致 |
| ADR-0002 | draft → accepted | 无问题，Consequences 非空 | 接受 | 已关闭 | 对照注册表 §2 决策一致 |
| ADR-0003 | draft → accepted | 无问题，Context 清晰 | 接受 | 已关闭 | 对照注册表 §10 决策一致 |
| ADR-0018 | draft → accepted | 无问题，与 ADR-0002 呼应 | 接受 | 已关闭 | 对照 §11.3 一致 |

## 后续

- 将 4 个 ADR 的 Status 从 `draft` 改为 `accepted`
- 更新 `docs/architecture/adr/README.md` 注册表（4 行状态 + 备注"含 M1 draft review record"）
