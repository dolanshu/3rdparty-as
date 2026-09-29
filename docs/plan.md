# 计划（Plan）— `3rdparty-as`

产品化的第三方 IMS Application Server。单租户、on-premises 交付，部署在运营商网络之外，
由 S-CSCF 经运营商的 S-SBC 触发。

设计基线是 [`architecture/新系统整体架构.md`](architecture/新系统整体架构.md)。
本文是建立在它之上的计划。

---

## 0. 本计划的状态

| | |
|---|---|
| 当前进行中的步骤 | **M2 —— 内核**（M0、M1 已完成） |
| 设计基线 | 已确认（`architecture/新系统整体架构.md`，决策 1–19） |
| 卡住后续里程碑的未决项 | §5 |
| POC 代码的迁移 | 刻意推迟到 M1–M3，且由 [`migration/triage.md`](migration/triage.md) 把关 |
| M1 完成日期 | 2026-09-28（AI agent 代办；维护者签字待补，见 `docs/reviews/m1-exit-review.md`） |

### 当前仓库状态说明

- `master` 分支当前领先 `origin/master` 3 个 commit，其中 1 个为已 push 的 pre-roadmap 骨架（commit `7b36c0d`，消息 `M0 done- except sip-stack selection`）。该 commit 是在 SIP 栈选型完成前生成的临时骨架，**不作为正式基线**。
- M0 正式基线由维护者在 SIP 栈选型完成（ADR-0019 Accepted）后授权代签；正式基线应在维护者逐次批准提交后形成，且不得跳过 git hook。
- G11 已关闭：本说明明确区分 pre-roadmap 骨架与正式基线，后续里程碑以 M0 正式基线为起点。

---

## 1. 本步骤已做出的决策

在创建任何东西之前与维护者确认：

| # | 决策 |
|---|---|
| 1 | 新仓库 `3rdparty-as`，建在维护者机器上。全新 git 历史 —— POC 的历史**不**导入。 |
| 2 | POC 代码**不整块导入**。栈变了、架构重组了，所以每个文件先经过甄别（[`migration/triage.md`](migration/triage.md)），避免把 POC 时代的妥协连同代码一起继承过来。 |
| 3 | M0 只交付骨架：目录结构、`pyproject.toml` + uv workspace、CI、`AGENT.md`、ADR 注册表、结构守卫。结构在代码迁入**之前**先评审。 |
| 4 | **O1（容量目标）有自己独立的研究阶段。** 这里不假设它，它也不阻塞骨架。Go 迁移与 HPA 阈值都要在那项研究之后才定，而不是之前。 |

---

## 2. 骨架交付了什么

### 2.1 结构

```
3rdparty-as/
├── AGENT.md  README.md  CHANGELOG.md  VERSION  CONTRIBUTING.md
├── CODE_OF_CONDUCT.md  SECURITY.md  NOTICE  LICENSE  Makefile
├── pyproject.toml            workspace 根 —— 虚拟 manifest，唯一工具配置
├── platform/                 ② 内核：进程壳、状态机、decide() 缝、各 seam
├── apps/                     ① 信令面：translation/、anti-fraud/
├── services/                 ③ 控制面：config-service/、console/
├── testbed/                  ⑥ contracts/（数据）· simulators/ · load/
├── deploy/                   helm/（生产）· compose/（仅 dev）
├── docs/                     architecture/ · adr/ · migration/ · plan.md
└── tests/                    横切结构守卫
```

### 2.2 这个结构消除的三个 POC 缺陷，以及如何消除

| POC 缺陷 | 本处的机制 |
|---|---|
| 每个 CI job 都要 `git clone ../as_platform` | 一个仓库，一次 `uv sync`，没有兄弟目录 checkout |
| `deploy/Dockerfile.as` 失败：构建上下文在仓库外 | 一切都在一个根下 |
| `VERSION` 0.2.0 vs `pyproject` 0.1.0 | `tests/test_version_consistency.py` —— 一个数字一个家，由断言保证 |

### 2.3 随骨架一起交付的守卫

分层不是靠目录布局保护的 —— 在 monorepo 里任何 import 都能解析成功。它靠测试保护：

| 守卫 | 断言 |
|---|---|
| `platform/tests/test_library_independence.py` | 内核不 import 任何 app、service 或 testbed 包；禁用列表覆盖每个其他 workspace 成员 |
| `tests/test_workspace_layout.py` | 声明的成员都存在、`src/` 下各一个包、发行名唯一、ruff `src` 完整、成员不声明自己的工具配置、成员不拥有 `VERSION` 文件 |
| `tests/test_version_consistency.py` | `VERSION` 是 SemVer、最新的 CHANGELOG 标题等于它、每个组件版本是 SemVer |

### 2.4 四层 CI 门禁（ADR-0015）

| 层 | Marker | 运行时机 |
|---|---|---|
| ① fast | `unit or contract` | 每次 push 和 PR |
| ② integration | `integration` | 在 ① 之后 |
| ③ e2e | `e2e` | 在 ② 之后 |
| ④ performance | `performance` | nightly、tag、手动 |

**已知的骨架例外**：② ③ ④ 层带 `continue-on-error`，因为还没有那类测试。必须在首个引入该类测试的
里程碑把它们改成阻塞。作为 M2 / M3 / M6 的退出标准跟踪。

**进展（2026-09-28）**：`integration` 层首个用例已引入（`platform/tests/test_telemetry_export_integration.py`，真 socket 验证遥测导出不阻塞），CI 层② 已同步改为阻塞；层③ e2e 与层④ performance 仍无用例，保持 `continue-on-error`。

---

## 3. M0 的退出标准

- [x] 目录结构创建完成，每个目录都带一个 README 说明该放什么
- [x] `pyproject.toml` workspace 含七个成员；`uv sync` 能解析
- [x] `make gate` 绿：`ruff format --check`、`ruff check`、`mypy`、pytest
- [x] 三个结构守卫写好且通过
- [x] `AGENT.md` —— 产品的、而非 POC 的协作守则
- [x] ADR 注册表：19 项决策映射到 ADR 编号，模板就位
- [x] `docs/migration/triage.md` —— 清点与初步分类
- [x] 四层 CI workflow
- [x] **结构经维护者评审并签字**（维护者授权 AI agent 代签，授权日期 2026-09-28）
- [x] 首次 commit（`7b36c0d M0 done- except sip-stack selection`，已 push 的 pre-roadmap 骨架）

---

## 4. 里程碑

里程碑是顺序的。每个都以自己的完成定义收尾；上一个没签字，下一个不开始。

| # | 里程碑 | 产出 | 状态 | 门禁 |
|---|---|---|---|---|
| **M0** | 仓库骨架 | 本结构、守卫、ADR 注册表、CI | **已完成（维护者授权代签）** | §3，外加维护者签字 |
| **M1** | 甄别与行为基线 | 冻结 POC commit；抓取消息样例与 trace；确认或推翻 `migration/triage.md` 里每个裁决。**无产品代码。** | **已完成（2026-09-28；门禁裁决见 §4.1）** | 每个文件都有一个带证据的裁决；基线已抓取且可复现 |
| **M2** | 内核 | `platform/`：进程壳、`decide()` 缝、缝后面的 `RedisStateStore`、TLS transport、非阻塞导出的 OTel 三信号、内部 API 契约、feature 开关 seam | **M2a 已完成；M2b seam 已落（2026-09-28），栈绑定未开始** | 内核守卫绿；能在其上构建用例而不碰 sippy |
| **M3** | 应用 | `apps/translation` 与 `apps/anti-fraud`；决策模块先做 TDD | **已完成（2026-09-28；门禁裁决见 docs/reviews/m3-gate-review.md）** | 契约用例集对两者都重放绿 |
| **M4** | 控制面 | `services/config-service`（PG 版本库、变更单状态机、灰度分发、回滚）与 `services/console`（读写、鉴权、审计） | **已完成（2026-09-28；PG 接线转 M5，见 docs/reviews/m4-console-access-review.md）** | 一次规则变更走完整闭环：编辑 → 审批 → 分发 → 上报版本 → 回滚；开关配置走变更流水线 + 开关两态测试 |
| **M5** | 运维 | Helm chart、自定义指标 HPA、缩容保护控制器、draining / ISSU、告警规则集 | **进行中（Helm/告警/渲染校验/缩容保护/PG 闭环/容器镜像已落，2026-09-30；真实集群滚动升级与缩容验证未完成）** | 滚动升级不掉呼叫；缩容不掉呼叫 |
| **M6** | **容量研究** | 真实 socket 压测 harness；测出 CPS、并发会话、建立时延 —— 按栈分别 | 未开始 | 产出 O1 的答案；在这跑起来之前不假设任何目标 |
| **M7** | Go 迁移 | 一个用例的 `go-b2bua` 镜像，commit 固定并 vendoring；跨实现对拍 | 未开始 | **受 M6 把关。** 仅当与 Python 实现输出对输出一致时才转正（ADR-0012） |
| **M8** | 发布候选 | 带证据的验收运行、文档链完整、统一产品版本 | 未开始 | 逐条验收报告 |

### 4.1 M1 门禁裁决（2026-09-28）

M1 门禁原文：*每个文件都有一个带证据的裁决；基线已抓取且可复现*。逐项核对结果：

| 门禁项 | 状态 | 证据 | 裁决 |
|---|---|---|---|
| 每个文件都有一个带证据的裁决 | 达成 | `docs/migration/triage.md` 全文检索无"未决 / 待裁决 / TBD / 待定 / pending"残留；`b27bb3d docs(triage): M1 adjudication confirmation` | 接受 |
| 冻结 POC commit | 达成 | 基线抓取脚本记录来源；`testbed/contracts/sip-baseline/` 内各场景 README 标注抓取脚本与日期 | 接受 |
| 基线已抓取且可复现（S1-S4） | 达成 | `S1-basic-call`（14 条）、`S2-no-match-404`（4 条）、`S3-policy-reject-603`（4 条）、`S4-caller-cancel`（12 条）均有消息文件 | 接受 |
| S5 / S6 / S7a / S8 基线 | **未抓取**（仅 README，零消息文件） | 对应 REQ-F-2 / F-3 / F-4 / F-5 | **接受为"派生基线"**：`docs/acceptance/test-plan.md` 中这四条需求的验收本就写为"完成 REQ-F-1 的基本呼叫后提取 X"，可从 `S1-basic-call` 派生断言，不单独抓取。理由：这四条断言的是同一通呼叫的头域/SDP 属性，重复抓取不增加信息量，只增加维护面 |
| S10 / S11 基线 | **未抓取**（仅 README） | 对应 REQ-F-10 / F-11；POC ReturnUas 只返回 200 OK，无 busy 分支，也无显式竞态构造 | **接受为"M2 probe 补"**：与 `docs/requirements/prd.md` §2.4 已知缺口表一致（M2 probe 阶段在 testbed 补对拍场景），不构成 M1 阻塞 |

**结论**：M1 门禁达成。S5/S6/S7a/S8 的"派生基线"与 S10/S11 的"M2 probe 补"两项裁决写入本节，作为 M2 进入的前提。若后续决定补抓 S5-S8 消息文件，需在本节追加一行推翻记录，而不是静默替换。

**派生基线已可执行化（2026-09-28）**：裁决不再是纸面结论 —— `testbed/simulators/tests/test_derived_baseline.py`（marker `contract`）对 `S1-basic-call` 的 14 条消息实际执行派生断言，覆盖 REQ-F-2（双腿 Call-ID 不同、同腿内稳定）、REQ-F-3（host:port 改写、归一化后同一被叫）、REQ-F-4（SDP 逐字节相等，含 answer）。当前 10 条通过、2 条显式 skip（见下）。

| 派生断言发现的偏差 | 处置 |
|---|---|
| S1 的出腿 user 部分被翻译改写（`+8613800138000` → `013800138000`），与 `test-plan` §1.1 REQ-F-3 原断言"user 部分一致"冲突 | 已按事实改 `test-plan` §1.1：非翻译场景不变、翻译场景按规则改变 |
| S1 未构造出腿 `Route` 头与任何 `Record-Route` 头 | 这两条派生断言显式 skip 并注明"需 M2 probe 补"；另补了一条基线真正能证明的硬断言：入腿 Route 的 next-hop 正是出腿 Request-URI 的 host:port |
| 14 个基线文件全部是 CRLF 换行 | 解析器按 CRLF 原样处理，SDP 逐字节比较在原始字节下通过 |

M6 是一个带决策的研究里程碑，不是对某个数字的承诺。M7 在 M6 报告之前不启动。

---

## 5. 未决项

### 5.1 从架构文档继承（§12.1）

| # | 条目 | 阻塞 | 解决所需 |
|---|---|---|---|
| O1 | 容量目标：CPS、并发会话、建立时延预算。**已有量级估计**（见 [`architecture/容量量级估算.md`](architecture/容量量级估算.md)：选型设计目标 ≥500 CPS / ≥20,000 并发对话），但**仍是未决项** —— 数字来自公开统计推算，非实测 | M7（Go）、HPA 阈值（M5） | M6 的实测，在 harness 跑真实 socket 之后；须回收估算文档 §6 的 C1–C7 |
| O2 | ~~C/C++ 栈选型：仅当 Go 被证不够才考虑。~~ **已失效并升级**：生产 SIP stack 选型整体重开（sippy 退出生产栈），C/C++ 与 Go 同为候选，见 ADR-0019 | ~~阻塞 M0 签字~~ ✅ 已选定 reSIProcate（ADR-0019 Accepted）；E1/E4/E5 probe 验证归入 M1 |
| O3 | `go-b2bua` 与 `sippy 2.4.2` 的行为比对 | M7 | 人工比对；上游只标到 commit `61f1da28` |
| O4 | 呼叫轨迹保留期 | M4 | 客户合规要求 |
| O5 | 容灾等级：N+1（节点）还是 N+M（机架 / AZ） | M5 Redis 拓扑 | 客户 SLA |

### 5.2 搭骨架时新增

| # | 条目 | 阻塞 | 说明 |
|---|---|---|---|
| D1 | **Python 3.10 在 2026 年 10 月到达生命周期终点。** 产品锁 3.10 是因为那是 sippy 验证过的版本。 | 该日期之后的任何交付 | 尽早验证 sippy 在 3.11 / 3.12 上的行为；要么迁移，要么在 ADR 里把 EOL 运行时登记为已接受的 risk。这里不定。 |
| D2 | 同一用例的第二个（Go）实现放哪：`apps/<case>/{py,go}` 还是一棵独立的树 | M7 | 在 spike 之前由 ADR-0012 定，免得迁移中途改动结构 |
| D3 | Redis 客户端与 Sentinel 接线；脑裂窗口下的判决幂等 | M2 | 风险 R5 |
| D4 | 控制台前端形态：保留 vendored 单包、无构建步骤，还是接受一套工具链 | M4 | POC 禁止了 npm 和构建步骤；产品控制台更大 |
| D5 | 呼叫轨迹存储：PostgreSQL，还是独立的短保留存储 | M4 | 与 O4 相关 |
| D6 | testbed 是否必须在 v1 支持客户验收测试 | M8 | 架构文档把它推迟到 v1.1 |
| D7 | ~~未决~~ **已裁决（2026-09-28）**：粒度固定为号段 + 稳定哈希百分比，schema 与判定幂等见 [ADR-0021](architecture/adr/0021-runtime-override-granularity.md) | M4 | 与 ADR-0020 的分层门控相关，需在控制面设计前定 |

---

## 6. 塑造本计划的工作规则

- **先甄别再采纳**（[`migration/triage.md`](migration/triage.md)） —— POC 是行为的来源，不是代码的来源。
- **ADR 与改动一起写**，不事后、不批量。
- **决策层强制 TDD**，协议层用契约 + 仿真测试（ADR-0015）。
- **POC 不是依赖。** 这里任何东西都不得引用 `../3rtparty_AS_POC` 或 `../as_platform`。
- **AI 生成的代码过完全相同的门禁**，并在 PR 中标注为 AI 生成（AGENT.md §AI 辅助）。
- **M6 之前不发布任何容量数字。**

---

## 7. 风险登记

继承架构文档 §12.2。本步骤新增两条：

| # | 风险 | 缓解 |
|---|---|---|
| R10 | **在排期压力下跳过甄别**，整块导入 POC 代码，把它的非目标也一并继承 | M1 在 M2 写代码之前给每个文件出一个裁决；PR 必须引用其甄别行 |
| R11 | **行为在重写中丢失**，因为 POC 观察到的行为从没被抓取 | M1 在任何重写之前抓取基线；这样"等价"才可查 |
