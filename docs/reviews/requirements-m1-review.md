# Requirement 清单 Review Record

> 评审人：AI agent（grilling session + 素材追溯）
> 日期：2026-09-28
> 评审对象：`docs/requirements/README.md`（首次创建）
> 评审结论：**通过**

## 评审范围

覆盖 M0/M1 阶段已做的所有决策和 POC 基线行为。分三类：
- REQ-F 功能需求：来自 POC 基线 S1-S11
- REQ-NF 非功能需求：来自 POC 已知缺陷 + AGENT.md 红线 + ADR Context
- REQ-G 治理需求：来自 AGENT.md §3 + ADR-0020

## 评审方法

逐条核对来源：
1. **REQ-F 每条**：对照 `testbed/contracts/sip-baseline/` 对应 S 场景 README + 消息文件
2. **REQ-NF 每条**：对照对应 ADR 的 Context 节 + AGENT.md 行号
3. **REQ-G 每条**：对照 AGENT.md 原文

## 评审发现

### Gap 1：REQ-F-9/REQ-F-10/REQ-F-11 缺失 POC 基线

| 需求 | POC 状态 | 裁决 |
|---|---|---|
| REQ-F-9 in-dialog 路由 | POC 有 chained topology，但 capture_call.py 不跑，无独立消息样例 | 接受：标注为"M2 probe 阶段补"，不阻塞 requirement 文档发布 |
| REQ-F-10 非 2xx 分支 | POC ReturnUas 只返回 200 OK，无 busy 分支 | 接受：同上 |
| REQ-F-11 CANCEL 竞态 | POC 无显式竞态测试 | 接受：同上 |

这三条是 **POC 覆盖度本身的缺口**，不是 requirement 清单的漏项。

### Gap 2：已有 ADR 未引用 REQ 编号

已有 ADR（0001/0002/0003/0018/0019/0020）的 Context 节隐含了 requirement，但没有显式写"本 ADR 回应 REQ-*"。

| 裁决 | 状态 |
|---|---|
| 接受：M2 开始时统一补 | 待修改 |

本次补课不追溯修改 ADR 正文。M2 的第一个改动就是：
1. 每个已有 ADR 加 `对应 REQ` 元数据行
2. 每个 REQ 条目已经有对应 ADR 标注（正向链接存在）

### Gap 3：没有 REQ-S-*（安全需求）类别

AGENT.md 提到 TLS（ADR-0019）和证书热轮换缺口，但没有独立安全需求章节。

| 裁决 | 状态 |
|---|---|
| 接受：当前 NFR 里已隐含（REQ-NF-5 S-SBC 桥接 → TLS 隐式覆盖）。如 M2 引入 TLS 外置组件，再新增 REQ-S-* 分类 | 已关闭 |

### Gap 4：容量需求未 formalize

架构文档有容量估算，但没有 REQ-NF-* 条目对应。AGENT.md L38 说"M6 实测之前不发布容量数字"，容量目标本身在 M0/M1 阶段没有冻结。

| 裁决 | 状态 |
|---|---|
| 接受：容量需求归入 M2，对应 O1 独立研究 | 待立项 |

## Adjudication

| Gap | 来源 | 问题摘要 | 裁决 | 修改方案 | 状态 | 验证方式 | 备注 |
|---|---|---|---|---|---|---|---|
| 1 | POC 基线 | REQ-F-9/10/11 无 POC 消息样例 | 接受 | requirement 文档标注"M2 补" | 已关闭 | 文档标注可查 | 不是 requirement 漏项，是 POC 能力边界 |
| 2 | ADR 一致性 | 已有 ADR 未显式引用 REQ 编号 | 接受（M2 补） | M2 第一个改动：所有 ADR 加 `对应 REQ` 元数据行 | 待修改 | M2 commit 验证 | 正向链接（REQ→ADR）已存在 |
| 3 | 分类完整性 | 无 REQ-S-* 安全类别 | 接受 | NFR 已隐含覆盖；M2 按需新增 | 已关闭 | 文档审阅 | — |
| 4 | 容量需求 | 容量目标未 formalize | 接受 | 归入 M2 O1 研究 | 待立项 | M2 O1 产出 | AGENT.md L38 约束 |

## 评审结论

Requirement 清单通过。4 个 Gap 全部裁决接受，其中 2 个待 M2 跟进，不阻塞当前文档发布。

评审人确认：
- 所有 REQ-F 条目来源可追溯
- 所有 REQ-NF 条目已对应已有 ADR
- 格式符合 AGENT.md §3 定义
- 补课说明与 ADR 的向后关系清晰
