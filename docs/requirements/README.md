# Requirement 清单

> Requirement 是设计、编码、测试和验收的唯一标准。
> 每条 requirement 标注：来源、对应 ADR、验收方式。
> 格式：REQ-F-*（功能）/ REQ-NF-*（非功能）/ REQ-G-*（治理）。

## 格式说明

| 字段 | 含义 |
|---|---|
| 编号 | REQ-F-*/REQ-NF-*/REQ-G-* |
| 描述 | 一句话说清"系统必须做到什么" |
| 来源 | 触发这条 requirement 的上游文档/POC 行为 |
| 对应 ADR | 已存在的 ADR（决策层）；空 = 还没有对应决策 |
| 验收方式 | 设计/测试/代码层如何验证 |

---

## REQ-F-* 功能需求（Functional）

来自 POC SIP 行为基线（`testbed/contracts/sip-baseline/`），每条对应 S1-S11 中的一个场景。

| 编号 | 描述 | 来源 | 对应 ADR | 验收方式 |
|---|---|---|---|---|
| REQ-F-1 | 系统必须能处理基本呼叫：INVITE→100 Trying→180 Ringing→200 OK→ACK→BYE→200 OK，双躯干双核心四段转发 | POC 基线 S1 | ADR-0003（ISC 语义） | `testbed/contracts/sip-baseline/S1-basic-call/` 14 条消息 |
| REQ-F-2 | B2BUA 双腿：两侧 Call-ID 必须不同，URI 分别改写 | POC 基线 S5（S1 中验证） | ADR-0003 | S1 中 Call-ID 断言 |
| REQ-F-3 | Request-URI 改写：上游 trunk URI 改写为下游 core 路由 | POC 基线 S6（S1 中验证） | ADR-0003 | S1 中 URI 断言 |
| REQ-F-4 | SDP 完全透传：offer/answer 原样传递到对端，不在 AS 层做媒体锚定 | POC 基线 S7a（S1 中验证）；AGENT.md L20（不做媒体） | ADR-0004（不做媒体 seam） | S1 中 SDP 断言 |
| REQ-F-5 | Route/Record-Route 正确处理：上游 trunk Route 头传递、下游 core Record-Route 插入 | POC 基线 S8（S1 中验证） | ADR-0003 | S1 中 Route 断言 |
| REQ-F-6 | 无匹配规则返回 404 Not Found（非 403 Forbidden） | POC 基线 S2 | — | `testbed/contracts/sip-baseline/S2-no-match-404/` 4 条消息 |
| REQ-F-7 | 策略拒绝返回 603 Decline（非 403 Forbidden） | POC 基线 S3 | — | `testbed/contracts/sip-baseline/S3-policy-reject-603/` 4 条消息 |
| REQ-F-8 | Caller 放弃：CANCEL→200 OK→BYE→487 Request Terminated→ACK | POC 基线 S4 | — | `testbed/contracts/sip-baseline/S4-caller-cancel/` 12 条消息 |
| REQ-F-9 | in-dialog 请求路由：对话建立后，re-INVITE/UPDATE/INFO 正确路由到活跃对话 | POC 有 chained topology（未进基线 capture） | — | `testbed/simulators/` in-dialog 路由测试（M2） |
| REQ-F-10 | 非 2xx 分支处理：486 Busy Here / 480 Temporarily Unavailable / 408 Request Timeout | POC ReturnUas 只返回 200 OK，基线缺失 | — | probe 阶段补（M2） |
| REQ-F-11 | CANCEL 与最终响应竞态：CANCEL 到达后不再 accept 最终响应 | POC 无显式竞态测试，基线缺失 | — | probe 阶段补（M2） |

**已知缺口**：REQ-F-9 / REQ-F-10 / REQ-F-11 三个功能需求在 POC 基线上缺失，需要 probe 阶段补。这不阻塞 M1，但阻塞 M2 设计。

---

## REQ-NF-* 非功能需求（Non-Functional）

来自 POC 已知缺陷、AGENT.md 红线、ADR Context 节。

| 编号 | 描述 | 来源 | 对应 ADR | 验收方式 |
|---|---|---|---|---|
| REQ-NF-1 | 进程重启不丢会话：会话状态、对话状态、caller_state 全部外置 | ADR-0002 Context（POC InMemoryStateStore 缺陷） | ADR-0002 | StateStore seam 实现 + 重启恢复测试 |
| REQ-NF-2 | 单进程状态有界：一个用例一个进程，一个故障域 | ADR-0002 Context（POC sippy 阻塞模型硬约束） | ADR-0002 | `apps/` 目录结构 + K8s Deployment 拓扑 |
| REQ-NF-3 | 可水平扩展：HPA 能基于 active_calls/cps 独立扩缩每个用例 | ADR-0002 Consequences（进程无状态推论） | ADR-0002 | custom metrics + HPA 配置 |
| REQ-NF-4 | ISS（In-Service Upgrade）支持：draining 摘流后存量呼叫归零即升级 | ADR-0009（已 accepted） | ADR-0009 | draining 机制 + 零停机验证 |
| REQ-NF-5 | S-SBC 透明桥接：AS 侧看不到 "网外" 与 "网内" 两种语义差异 | ADR-0003 Context | ADR-0003 | S-SBC 仿真器 + ISC 行为一致性测试 |
| REQ-NF-6 | 不做媒体（RTP/转码/DTMF/MRF/媒体锚定） | AGENT.md §2 L20 | ADR-0004（seam） | 代码审查 + seam 注释 |
| REQ-NF-7 | 不做 CDR：用 Call-ID 呼叫轨迹替代 | AGENT.md §2 L21 | ADR-0017 | 代码审查 + 轨迹日志结构 |
| REQ-NF-8 | 不做合法监听（LI） | AGENT.md §2 L22 | ADR-0016 | 代码审查 |
| REQ-NF-9 | 单租户 on-premises 部署：每客户独立实例 | AGENT.md §2 L24-33 | ADR-0002 / 架构文档 §11 | Helm chart 结构 + 部署验证 |
| REQ-NF-10 | 配置不走 GitOps：PostgreSQL 行 + 变更单状态机 | AGENT.md §2 L34-36 | ADR-0006 | config-service 实现 + 控制台 CRUD |
| REQ-NF-11 | 版本单一来源：根 VERSION 文件，组件声明接口版本 | ADR-0018 Context（POC VERSION vs pyproject 漂移） | ADR-0018 | `tests/test_version_consistency.py` |
| REQ-NF-12 | monorepo + uv workspace 统一依赖管理 | ADR-0001 Context（POC CI clone 硬伤） | ADR-0001 | `pyproject.toml` workspace 配置 |

---

## REQ-G-* 治理需求（Governance）

来自 ADR-0020（feature capability gating）+ AGENT.md §3 工程纪律。

| 编号 | 描述 | 来源 | 对应 ADR | 验收方式 |
|---|---|---|---|---|
| REQ-G-1 | 每个 feature 必须显式裁决 enablement（开关默认关、灰度策略、移除条件） | ADR-0020 Context | ADR-0020 | HLD/LLD 每 feature 节 + 开关测试 |
| REQ-G-2 | 改动必须贯通文档链：requirement → ADR → 设计 → 契约 → 代码 → 验收 | AGENT.md §3 L42-56 | — | PR checklist + 代码 review |
| REQ-G-3 | 代码必须标注对应 ADR：不显而易见的代码带 `# See ADR-00NN` | AGENT.md §6 L121 | ADR-0015（accepted） | AST 扫描守卫（`tests/`） |
| REQ-G-4 | make gate 必须全绿才能提交 | AGENT.md §9 | — | CI 门禁 + pre-commit hook |

---

## 与 ADR 的关系（补课说明）

本清单是在已有 ADR（0001/0002/0003/0018/0019/0020）之后创建的。按 AGENT.md §3.1 的理想顺序，requirement 应在 ADR 之前。**本次是补课，不追溯修改 ADR 的 Context 节**；M2 开始时所有新 ADR 必须先写 requirement，再写 ADR。

已有的 ADR Context 节隐含了 requirement，本清单把它们显式化。M2 应完成双向引用：ADR 加"本 ADR 回应 REQ-*"字段，每个 REQ 条目也已标注对应 ADR。
