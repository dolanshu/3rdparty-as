# AGENT.md — 3rdparty-as

> 人与 AI agent 的协作守则（rules of engagement）。
> 在写任何代码之前先读这个文件。如果这里的规则与某条请求冲突，以本文件为准，并向维护者提出冲突。

## 1. 项目定位与范围

一个**产品化的第三方 IMS Application Server（应用服务器）**：单租户、on-premises（本地部署），部署在运营商 IMS 网络之外，由 S-CSCF 经运营商的 S-SBC 触发，S-SBC 做透明桥接。

它**不是 POC**。POC（`../3rtparty_AS_POC`）是在另一套非目标下验证概念而存在的；本仓库是产品本身。

**我们只实现外部 AS。** S-CSCF、S-SBC 和 HSS 是运营商的；它们在这里只作为 `testbed/` 下的仿真器出现。

定位细节、架构图和 19 项已确认决策见 [`docs/architecture/新系统整体架构.md`](docs/architecture/新系统整体架构.md)。里程碑、未决项和当前状态见 [`docs/plan.md`](docs/plan.md)。

## 2. 非目标

明确不在范围内。每一项都是经过决策的结果，不是疏漏：

- **不做媒体。** 没有 RTP、没有转码、没有 DTMF、没有 MRF、没有媒体锚定。保留一个 seam 并写明触发条件（ADR-0004）。
- **不做 CDR。** 不采集、不投递、不归档、不批价。用按 Call-ID 的呼叫轨迹替代它，用于投诉追溯与反诈举证（ADR-0017）。
- **不做合法监听（LI）。** IRI 属于网内网元；让第三方 AS 介入会引入跨法域暴露（ADR-0016）。
- **不做 Diameter Sh。** 数据来自我们自己的数据面。
- **不做多租户。** 单租户、on-premises。选择依据：

  | 维度 | 单租户 | 多租户 |
  |---|---|---|
  | 部署 | 每客户独立实例，on-prem 交付 | 共享实例，逻辑隔离 |
  | 隔离 | 天然物理隔离，故障域独立 | 需租户级命名空间 + 访问控制 |
  | 运维 | 升级窗口按客户协商，互不影响 | 一次变更影响全部租户 |
  | 合规 | 数据不出客户机房，审计边界清晰 | 跨租户数据泄露风险需额外证明 |

  运营商的交付形态本身就是一客户一系统，多租户在此场景无收益。
- **配置不走 GitOps。** 不能要求运营商运维人员为了改一个号段去学 Git；版本存为 PostgreSQL 中的行，藏在变更单状态机之后（ADR-0006）。
  变更路径：控制台 / 内部 API 提交变更单 → 审批 → 服务写入 PostgreSQL → 灰度分发。
  不是运维直接 UPDATE 数据库，也不是用 git 仓库管理配置。
- **不写 Operator（CRD）。** 用 Helm + 标准 Deployment / ConfigMap / Secret（ADR-0013）。
- **M6 实测之前不发布任何容量数字。** 在真实 socket 压测测出之前，不公布任何 CPS 或并发数字。

## 3. 工程阶段与文档链

每一个行为改动都必须贯通整条文档链。Requirement 是设计、编码、测试和验收的**唯一标准**。缺少任一环节的改动不完整。

```text
需求（Requirement）
   ↓
架构决策（ADR）
   ↓
高层设计（HLD）+ 低层设计（LLD）
   ↓
接口契约与消息样例
   ↓
代码 + 测试
   ↓
验收项与 Review Record
```

### 3.1 阶段定义

| 阶段 | 产出 | 负责人 | 进入下一阶段的条件 |
|---|---|---|---|
| **Requirement** | `docs/requirements/` 中的 REQ-F-*/REQ-NF-* 条目 | 维护者 / 产品 | 评审通过，有 review record |
| **ADR** | `docs/architecture/adr/00NN-*.md` | 维护者 / 架构 | 评审通过，有 review record |
| **HLD/LLD** | `docs/architecture/hld.md`、`docs/architecture/lld.md`（含 feature enablement 设计） | 维护者 / 架构 | 评审通过，有 review record |
| **Interface Contract** | `testbed/contracts/` 中的用例、消息样例 | 维护者 / 开发 | 与 ADR 一致，有 review record |
| **Code + Test** | 实现代码 + 对应测试 | 开发 / AI agent | `make gate` 绿，PR 引用 ADR 和 requirement |
| **Acceptance** | `docs/acceptance/report.md` 中的证据 | 维护者 | 验收项逐项通过，有 review record |

### 3.2 文档要求

- **每个阶段都必须有文档。** 没有文档的决策等于没有发生过的决策。
- **Requirement 是唯一标准。** 设计、代码、测试、验收都必须能追溯到具体的 REQ-* 编号。
- **所有文档必须有 review。** 评审不是可选步骤；每个阶段的产出必须经过 review 才能进入下一阶段。
- **Review 必须有单独的 review record。** 评审意见、修改记录、签字状态写入 `docs/reviews/` 下的独立文件（例如 `docs/reviews/adr-0019-review.md`）。口头或 inline comment 不构成正式评审记录。
- **推翻或修改上游文档时，必须同步更新整条链。** 只改代码不改 requirement/design/acceptance 是未完成。

### 3.3 Review Record 格式

每个 review record 至少包含：

1. 评审对象（文档 / PR / commit range）
2. 评审日期与评审人
3. 评审结论：通过 / 有条件通过 / 不通过
4. 发现的问题清单与对应修改
5. 修改后的确认签字

### 3.4 新 Feature 的实现流程

与 §3 的文档链对应，每个新 feature 逐阶段推进：

1. **REQ** —— 需求条目进入 `docs/requirements/`。
2. **ADR** —— 显式裁决 **enablement**（是否引入开关、默认态、灰度、移除条件）。
3. **HLD/LLD** —— 落在设计文档里：开关如何分层、如何判定、如何回滚。
4. **契约** —— 开关只做能力启停、**不改接口契约**；关闭走既有默认路径。
5. **代码 + 测试** —— 开关的**开 / 关两态**都要有测试（§6）。
6. **验收** —— 按开关态取证（§14）。

**规则**：每个 feature 必须显式裁决**是否引入开关**；引入即须写明**默认态、灰度策略与移除条件**（防开关债务）。机制见 [ADR-0020](docs/architecture/adr/0020-feature-capability-gating.md) 与 [`docs/architecture/新系统整体架构.md`](docs/architecture/新系统整体架构.md) §5.3。

## 4. 分层

```text
apps/  ──uses──▶  platform/          一个用例一个进程
services/ ─────────────────────────▶  PostgreSQL、AS 内部 API
testbed/ ──may use──▶ platform/       研发资产，绝不做运行时依赖
```

**内核绝不能 import 应用、服务或 testbed。** 仓库边界并不强制这一点 —— 在 monorepo 里任何 import 都能解析成功。靠 [`platform/tests/test_library_independence.py`](platform/tests/test_library_independence.py) 来强制，[`tests/test_workspace_layout.py`](tests/test_workspace_layout.py) 来强制结构本身。

一个 app 绝不能 import 另一个 app。一个用例是一个进程、一个故障域、一个灰度单元。

目录结构和成员清单见 [`docs/plan.md`](docs/plan.md) §2。

## 5. 编码约定

- **产物的语言：英文。** 标识符、注释、日志、错误字符串、commit message、贴近代码的文档都用英文。本仓库中面向人的文档用中文；这是唯一的例外。
- **所有公共函数都要类型标注；`mypy` 严格模式必须干净。**
- **决策模块是纯函数。** 产出判决的模块里不能有 socket、不能有时钟、不能有全局状态。这正是 TDD 在那儿便宜的原因。
- **SIP 栈的交互只局限在 SIP adapter 和 call controller。** 胶水层保持轻薄。
- **`ED2.loop()` 或等价的阻塞事件循环是阻塞的。** 绝不要在 SIP 回调里调用阻塞操作 —— 包括遥测导出。导出在自己的线程上跑（ADR-0005）。
- **每一行不显而易见的代码都指向它的 ADR**：`# See ADR-00NN`。审稿人必须能从代码一步走到理由。
- **`src/` 里不要出现 `util`、`helper`、`misc`、`common`、`tools` 这类模块名。**
- **SIP 栈的行为是观察出来的，不是假设的。** 有疑问就在 `testbed/` 下写一个 probe 跑一下。绝不要凭空发明一个 header、状态码或 API。

## 6. 测试策略

测试必须与 requirement 对齐。每个测试都应能追溯到至少一个 REQ-* 或契约用例。

| 层 | Marker | 方法 |
|---|---|---|
| 决策逻辑 | `unit` | **强制 TDD**，红 - 绿 - 重构。TDD 的回报就在这里。 |
| 契约 | `contract` | 声明式用例，放在 `testbed/contracts/`，对**每一个**实现重放 |
| 协议 / 接入 | `integration` | 契约测试 + 仿真对等端；不做严格 TDD —— 成本高、回报低 |
| 完整流程 | `e2e` | 完整呼叫 + 错误分支，含控制台 |
| 容量 | `performance` | 只用真实 socket。绝不要靠驱动回调来测 —— 那测的是业务逻辑，不是系统（ADR-0014） |

**feature 开关的开 / 关两态必须在对应测试层被覆盖**（机制见 [ADR-0020](docs/architecture/adr/0020-feature-capability-gating.md)）。

测试端口必须可配置，避免并行运行时端口冲突。

## 7. ADR

每一个架构决策都在 `docs/architecture/adr/` 里留一条记录。注册表把已确认决策映射到 ADR 编号，见 [`docs/architecture/adr/README.md`](docs/architecture/adr/README.md)。

- ADR 与它所授权的改动**一起**写，不事后补，也不批量补。
- ADR 必须写明它接受的缺口。空的 consequences 节等于没分析完。
- 推翻一个决策意味着新增一个 ADR，**并且**在同一次改动里更新 [`docs/architecture/新系统整体架构.md`](docs/architecture/新系统整体架构.md)。
- POC 的 ADR-0001…0016 **不**导入。它们描述的是另一个系统。可以引用它们作背景，但不能把它们当作有约束力的。

## 8. 版本与依赖

- **`./VERSION`** 是产品 release 版本的唯一源头。一次交付一个号，因为运营商收到的是一个系统。
- **`<member>/pyproject.toml`** 携带该组件自己的接口版本。
- **任何成员都不得拥有 `VERSION` 文件。** 一个数字两个家，正是本仓库要消灭的漂移（ADR-0018）。由 [`tests/test_version_consistency.py`](tests/test_version_consistency.py) 守卫。
- **SIP 协议栈由 ADR-0019 决定。** 在 ADR-0019 接受之前，`platform/` 不绑定任何具体 SIP 栈。POC 使用的 `sippy==2.4.2` 仅作为 `testbed/` 中抓取行为基线的参考工具，不进入产品生产依赖。
- 每个依赖都走 `uv`，提交 `uv.lock` 并在 CI 中校验。

## 9. 门禁（Gates）

`make gate` = `ruff format --check` → `ruff check` → `mypy` → pytest（unit/contract 层）。

CI 跑同样的四层：① 快（`unit or contract`）→ ② 集成 → ③ e2e → ④ 性能（nightly / tag 触发）。

本地门禁不绿，什么都不能提交。**本地门禁不是 CI**：绝不要把本地重跑冒充成 CI 结果。

**M0 骨架阶段说明**：当前 integration、e2e、performance 层没有测试。CI 通过 `continue-on-error` 绕过；本地 `make test` 在该阶段会因 pytest 无测试而失败。因此 `make gate` 在 M0 只跑 ① 层。首个引入某层测试的里程碑必须同步把该层改为阻塞。

## 10. AI 辅助与 Subagent 协作

1. AI 生成的代码过**完全相同**的门禁。不会因为是生成的就降低标准。
2. 含 AI 生成工作的 PR 要**标注出来**，方便审稿时相应加权。
3. Go 镜像移植是本项目收益最高的 AI 任务 —— 同构翻译 + 对拍 harness。要利用这个杠杆；但标准不放。

### 10.1 Subagent 模式（派发的唯一权威说明）

- **在接任务时判定，不是在写文件时判定**：接到任务先判断它是否会产生文件改动（新建 / 编辑 / 删除）。会 —— 在动手做任何其他事之前先派 writing subagent；主 agent 只做规划与 review。
- **主 agent 不写代码、不写文件。** 主 agent 负责规划、拆分任务、review subagent 输出、向维护者汇报。

**先认 IDE —— 两个 IDE 的派发机制不同，用错会静默退化成只读**（本仓库 M0 已经踩过这个坑）：

| IDE | 只读（探索 / 调研 / 代码搜索） | 可写（任何文件改动） |
|---|---|---|
| **Trae** | `Agent` 工具，`subagent_type = Explore` | `Agent` 工具，`subagent_type = general-purpose` |
| **CodeBuddy** | `Task` 工具，不传 `name`，`subagent_name = code-explorer` | `Task` 工具，**传 `name`**（角色标签，如 `m0-writer`，即 team mode）+ `mode = "acceptEdits"` |

> 判断依据：手上有哪个工具就用哪个。CodeBuddy 里**不存在** `general-purpose` / `Explore`，按名字调用会报
> `Subagent "general-purpose" not found`；**此时不得退回主 agent 自己写文件**，改用它自己的 team mode（传 `name`）。
> 反之在 Trae 里用 `Agent` 工具 + `subagent_type` 是正确的，不要照搬 CodeBuddy 的写法。

派发 writing subagent：

1. `prompt` 必须自包含：目标、边界、验证命令、报告格式，以及全部硬约束（如"不许运行 git commit"、"只许改这一个文件"）。CodeBuddy 另需 `name` 与 `mode = "acceptEdits"`（传 `name` 即自动开启 team mode 并建团，无需单独 `team_create`）。
2. subagent 报告完成后，主 agent 用 `git status` / `git diff` 核对实际改动，与其自述比对。
3. 确认无误后关闭该 writer，**然后**再启动下一个。

- **一个工作树同时只能有一个 writing subagent。** Git 状态是每工作树一个；第二个 writer 的改动会落到错误分支或互相覆盖，且失败是静默的。
- **Spawn prompt 必须自包含**：追加消息只在下一个 turn 边界被读取，**无法打断正在跑的 turn**（§10.3）。
- **派不出 writable subagent 时的处置**：① 先按上表确认当前 IDE 与模式；② 仍不可用则**停下来报告维护者**，由维护者显式批准主 agent 直接写。**绝不自作主张自己写。**
- **Trust but verify：** 主 agent 必须用 `git status` / `git diff` 核对 writing subagent 实际改动的文件，与其自述报告比对。Subagent 的总结描述的是它的意图，不一定是它实际做的事。
- **主 agent 自检**：每个 turn 结束前回答"我这一 turn 有没有直接写过文件？"。有 —— 立即停止并向维护者报告。

### 10.2 Context 管理

- **Context 接近上限时必须立即通知维护者**，不得静默工作到自动压缩发生。通知内容：(1) 当前落盘状态盘点（用 `git status` 核对）；(2) handoff 决策建议（开新对话 / 先补落盘 / 留在本对话）。
- **凡"只存在于对话里、丢了无法恢复"的决策，必须先落盘再开新对话。** 落盘去向：裁决进 ADR / gap review，状态进 `docs/plan.md`，调研结论进 `docs/` 专门文档。
- 具体流程见项目 skill `.trae/skills/context-handoff/`。

### 10.3 任务派发与同步

- Subagent 是无状态的：每次调用只返回最终结果，中间过程不可见。spawn prompt 必须自包含 —— 目标、边界、验证命令、报告格式全部写进去。
- **所有硬约束必须放在 spawn prompt 里**（例如"不许运行 git commit"、"只许改这一个文件"），而不是依赖后续消息。
- 需要追问或追加指令时：subagent 仍在运行用 `SendMessage`（CodeBuddy）或等效的追加消息机制；已完成则用 `resume` 参数（Trae）续接其上下文。不要为追问而重新 spawn 一个新 subagent。
- Subagent 在做出昂贵修改前（加依赖、改 schema、删代码、commit）必须先停下来报告。

### 10.4 Handover 协议

每个里程碑 conversation 的**开场仪式**：

1. 读 `AGENT.md`（本文件）
2. 读 `docs/README.md`
3. 读 `docs/plan.md` 中当前里程碑章节
4. 读 `docs/acceptance/criteria.md` 中该里程碑的验收项
5. 确认当前分支（由维护者命名或批准）
6. **首任务 subagent 判定**：收到维护者的首个任务时，先判断是否涉及文件改动（新建 / 编辑 / 删除）。是 —— 立即派 writing subagent，再做其他规划或讨论；否 —— 进入只读模式。

**结束仪式**：

1. 跑 DoD，把结果写入 `docs/acceptance/report.md`
2. 更新 `docs/plan.md` 状态和下一里程碑入口
3. 更新 `CHANGELOG.md` 和 `VERSION`
4. 不写 tag：tag 是维护者的步骤

## 11. Git 规则

- **未经维护者在该次对话中明确批准，绝不 push。** 不是 push、不是 force-push、不是 tag。
- **Agent 不创建分支。** 工作在维护者指定的分支上进行。每个分支要有明确目的和结束条件。
- **未经逐次、显式的批准，任何东西都不能进 `main` / `master`。**
- **Conventional Commits**，英文，一次 commit 一个逻辑改动：`feat` · `fix` · `docs` · `refactor` · `test` · `chore` · `build`。
- **不跳过 hook。** `--no-verify` 及其等价物禁止。如果 hook 挡住了 commit，去修原因。
- **绝不提交密钥、证书或真实流量抓包。**
- 一个行为改动要贯通整条文档链：需求 → ADR → 设计 → 接口契约 → 验收项 → CHANGELOG。

## 12. 从 POC 采纳代码

**绝不整块照搬。** 见 [`docs/migration/triage.md`](docs/migration/triage.md)。

- 每个 POC 文件在写产品代码之前都要有一个裁决 —— adopt / rewrite / baseline-reference / discard —— 且要有证据。
- 被采纳的代码**带着它的测试**一起过来。
- POC 的行为基线要在任何重写**之前**抓取，这样“等价”才是可查的断言。
- 本仓库必须能在**不引用** `../3rtparty_AS_POC` 或 `../as_platform` 的情况下构建、测试、运行。

## 13. 安全

- 不提交任何敏感信息：没有密钥、证书、token 或真实地址。
- trunk 是不可信的。对端要按白名单校验，并且与 S-SBC 端到端终止 TLS —— 任何人只要能伪装成 S-SBC，就能灌入呼叫（ADR-0016）。
- 证书轮换是配置热更新。绝不能重启进程，也不能丢掉在途呼叫。
- 载荷日志是显式、可开关的；日志里默认关闭。
- 每个控制台操作都要鉴权并审计。

## 14. 完成定义（Definition of done）

- [ ] 对着仿真对等端端到端跑通
- [ ] 在改动所属的层补了测试；`make gate` 绿
- [ ] `ruff format`、`ruff check`、`mypy` 干净
- [ ] 改动带了 ADR；若决策有移动，`docs/architecture/新系统整体架构.md` 已更新
- [ ] README 与受影响文档已更新（新 env var、端口、命令、目录）
- [ ] 有 CHANGELOG 条目；若交付内容变化则产品版本号已 bump
- [ ] 若采纳了 POC 代码：已引用对应的 triage 行
- [ ] 没有提交任何密钥
- [ ] 文档链完整：requirement → ADR → HLD/LLD → 契约/消息样例 → 验收项 → review record
- [ ] 若引入 feature 开关：开 / 关两态都有测试与验收证据，且写明移除条件

## 15. 未决项

未决清单和风险登记由 [`docs/plan.md`](docs/plan.md) §5 持有。不要悄悄解决一个未决项：如果一项工作强行逼出了一个决策，去写 ADR 并移动 `plan.md` 中的那一行。

其中最大的 O1（容量目标）有自己独立的研究里程碑（M6）。在它跑起来之前，不假设任何容量数字。
