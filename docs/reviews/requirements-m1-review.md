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
| 5 | PRD 重写 | PRD 格式/内容 8 项修正（见下 Gap 5） | 全部接受 | 已全部落实 | 已修改 | PRD v0.1 文件 | 2026-09-28 维护者修改意见 |
| 6 | PRD 剥离设计 | PRD 混入设计细节 + 技术注解不属于 requirement（见下 Gap 6） | 全部接受 | 剥离设计、删技术注解、新建 design 占位 | 已修改 | PRD v0.1 文件 vs design 目录 | 2026-09-28 维护者 review 第二轮 |

## Gap 5（PRD 重写 — 维护者 2026-09-28 修改意见）

PRD 从架构速查表重写为从上往下的正式 PRD 后，维护者提出以下 8 条修改意见，全部落实。

| # | 修改意见 | 裁决 | 状态 |
|---|---|---|---|
| 1 | 信令流程没标协议标准（RFC 3261 / 3GPP TS 24.229） | 接受：所有信令 REQ 标注 RFC 章节 | 已修改 |
| 2 | requirement 里不该有"对应 ADR"字段 — 顺序反了，应该 ADR 反向引用 REQ | 接受：PRD 删所有"对应 ADR"；ADR 的"回应 REQ"反向链接保留 | 已修改 |
| 3 | 验收标准应该在 testplan，不该在 requirement | 接受：创建 testplan.md，PRD 里留占位 `（验收标准见 testplan §X.X）` | 已修改 |
| 4 | REQ-F-2"双腿分离"是实现细节，不是 requirement — 应该写 Call-ID 不同是 B2BUA 的 RFC 3261 要求 | 接受：重写为协议语言 | 已修改 |
| 5 | REQ-F-6/F-7 缺业务上下文 — 没说清楚什么业务场景触发、为什么选这个响应码 | 接受：加"什么时候触发、为什么选这个响应码" | 已修改 |
| 6 | requirement 应是正式文件，不该叫 README.md | 接受：改名为 prd.md + 新建 README.md 做目录索引 | 已修改 |
| 7 | 缺版本号和日期 | 接受：加 v0.1 (draft) + 2026-09-28 + 版本历史表 | 已修改 |
| 8 | 把以上内容加入 review record | 接受：本表即为记录 | 已修改 |

## Gap 6（PRD 剥离设计 — 维护者 2026-09-28 第二轮修改）

PRD v0.1 重写完成后，维护者在 review 时发现 PRD 混入了设计细节和技术注解。需求文档应只描述"需要什么"，不说"怎么做"。ADR 决策和实现暗示应剥离出去。

| # | 修改意见 | 裁决 | 状态 |
|---|---|---|---|
| 1 | PRD 混入设计："PostgreSQL 行"、"Redis 外置"、"monorepo + uv workspace"、"draining 摘流"都是 ADR 决策，不是需求 | 接受：业务描述改写为纯需求语言 | 已修改 |
| 2 | 27 条"技术注解"段全部是设计暗示，需求文档不应包含 | 接受：全删，原封不动移到 `docs/design/from-prd-notes.md` | 已修改 |
| 3 | 创建 design 占位目录，暂存剥离的技术细节供 M2 设计阶段参考 | 接受：新建 `docs/design/README.md` + `from-prd-notes.md` | 已修改 |

### 业务描述改写清单

| REQ | 原文设计暗示 | 改写后纯需求语言 |
|---|---|---|
| REQ-NF-1 | "会话状态...绝对不能只存在于进程内存里" | "进程重启或故障时，正在进行的呼叫不能断——会话状态、对话状态、业务处理状态必须持久化在进程之外" |
| REQ-NF-2 | "不做阻塞事件循环（POC 的 sippy 模型）" | "一个业务用例一个进程" |
| REQ-NF-3 | "HPA 能基于 active_calls 和 cps 这两个自定义指标" | "支持水平扩展：业务量增加时能增加处理实例，不影响存量呼叫；业务量减少时能安全缩容" |
| REQ-NF-4 | "流程是：新版本副本就绪 → 旧版本副本标记 draining → active_calls 归零 → 副本下线" | "版本升级或配置更新时，正在进行的呼叫不能断。新请求路由到新版本进程，存量呼叫继续完成" |
| REQ-NF-6 | "保留一个 seam（接口定义）" | "保留一个扩展接口定义" |
| REQ-NF-10 | "配置版本存为 PostgreSQL 中的行...变更路径是：控制台 → 审批 → 写入 PostgreSQL → 灰度分发" | "配置变更必须经过审批流程。变更必须可版本化、可追溯、可灰度发布、可回滚。不要求运维人员为改配置去学 Git" |
| REQ-NF-11 | "`./VERSION` 文件是产品 release 版本的唯一源头...pyproject.toml 只携带接口语义化版本" | "产品有且只有一个版本号，所有组件声明自己的接口版本。不允许多个组件各有不同的 release 版本" |
| REQ-NF-12 | "用 `pyproject.toml` 的 `[tool.uv.workspace]` 统一管理依赖。CI 每个 job 不再需要 `git clone ../as_platform`" | "所有组件在一个仓库内。CI 构建和容器构建不应因跨仓依赖而失败" |

### 保留的内容

- RFC 3261 / 3GPP TS 协议引用（这是协议标准，不是设计）
- 产品边界定位：单租户、on-premises、S-SBC 透明桥接
- 非目标：不做媒体/CDR/LI/Diameter Sh
- REQ-F-2 的 B2BUA 双腿 Call-ID 不同（RFC 3261 §12.1 协议规定）

## 评审结论

Requirement 清单通过。4 个 Gap 全部裁决接受，其中 2 个待 M2 跟进，不阻塞当前文档发布。

评审人确认：
- 所有 REQ-F 条目来源可追溯
- 所有 REQ-NF 条目已对应已有 ADR
- 格式符合 AGENT.md §3 定义
- 补课说明与 ADR 的向后关系清晰
