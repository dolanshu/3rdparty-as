# 计划（Plan）— `3rdparty-as`

产品化的第三方 IMS Application Server。单租户、on-premises 交付，部署在运营商网络之外，
由 S-CSCF 经运营商的 S-SBC 触发。

设计基线是 [`architecture/新系统整体架构.md`](architecture/新系统整体架构.md)。
本文是建立在它之上的计划。

---

## 0. 本计划的状态

| | |
|---|---|
| 当前进行中的步骤 | **M7.1 工程关门（2026-10-07）**：[`handoff/2026-10-07-m7.1-sim-platform-plan.md`](handoff/2026-10-07-m7.1-sim-platform-plan.md) §9。kind 上产品 AS 路径的 UDP/TCP/TLS、第一版五种呼叫、BYE 2xx、直达被网络策略丢掉。测试 CA 不签 REQ-S-2/S-3，页面不签 REQ-S-4，计数不是容量。**下一步**是重评 [`handoff/pre-m8-demo-review-plan.md`](handoff/pre-m8-demo-review-plan.md)，把故事接到这个平台（含 config-service 下发）。**M8 仍搁置**：只剩 Close 前不做真实运营商 S-SBC / 客户 K8s，见 [`acceptance/m8-environment-evidence.md`](acceptance/m8-environment-evidence.md) 与 [`handoff/2026-10-07-m8-next-step-plan.md`](handoff/2026-10-07-m8-next-step-plan.md)。发布镜像带 SIP 监听放在重开 M8 之前。此前状态保留如下：**M8 RC 产物就绪（2026-10-06）**：签收矩阵 [`m8-test-plan-matrix.md`](acceptance/m8-test-plan-matrix.md)、环境证据 [`m8-environment-evidence.md`](acceptance/m8-environment-evidence.md)、退出评审 [`m8-exit-review-2026-10-06.md`](reviews/m8-exit-review-2026-10-06.md)；退出签字待维护者。**M8 发布候选（2026-10-06 开工）** — 执行计划 [`handoff/2026-10-06-m8-release-candidate-plan.md`](handoff/2026-10-06-m8-release-candidate-plan.md)。`master` 已含 callload 工程切片（[`handoff/2026-10-06-callload-merge-to-master.md`](handoff/2026-10-06-callload-merge-to-master.md)）；M2/M6/M7 **工程完成**，维护者签收与 REQ 全绿在 M8 内闭合。下列为 **M2–M7 工程史实摘要**（非当前步骤）：**M5 工程关门（2026-10-04，维护者 chat 授权代签；已并入 `master`）**。**M2 P0 可复现路径**：仓库根 `make m2-native`（vendor 离线恢复 + 源码构建 + UDP S1 smoke，见 `docs/acceptance/m2-native-build-matrix.md`）。**当前进行：先完成 M2**（M2a 已完成；M2b 当前仅 transport-policy seam 工程切片：支持 IP-only / IP:port（含 IPv6 bracketed endpoint）/ certificate fingerprint token 匹配）。2026-10-04 已完成 reSIProcate tag `resiprocate-1.14.0`（commit `632e215c2ca9aee5416bfe1808851ea6fa380044`）最小构建并在 native probe 验证 S1 UDP/TLS loopback（TLS 在空 HOME 下通过，修复 trust 初始化后无 `503 Certificate Validation Failure`）；同日补充 `--tls` 非 external 自测（本地自签证书）结果：S2 返回 `404 Not Found` 并正常退出，S3 返回 `603 Decline` 并正常退出，S4 触发 UAC `CANCEL` 且 DUM 日志出现 `RemoteCancel`/`LocalCancel` 与 `487` 路径后正常退出（ACK 线包未独立抓取，不宣称已捕获）。同日另完成一次 external raw SIP INVITE over TLS 证据：以 `resip_probe --tls --external` 监听动态端口，`openssl s_client -CAfile ... -verify_ip 127.0.0.1` 校验证书后发送一条 `sips:` INVITE（Via/Call-ID/CSeq/SDP 完整），probe 日志确认收到该 INVITE（`tlsd=127.0.0.1`）并返回 `100 Trying`、`180 Ringing`、`200 OK`。该外部客户端未发送 ACK/BYE，因此该证据是一次 external SIP transaction/early dialog response，不是完整 call/dialog。另有一条 **partial、testbed-only** SIGHUP cert-swap smoke（成功证据为 Contact 修正后的 90 秒 hold run）：一条 active S1 在 hold 期间触发 reload 调用后完成 BYE；该次 UAS 收到 BYE 的日志行包含 `tlsd=127.0.0.1`，且 Request-URI/Contact 指向 TLS listener 端口（`sips:` Contact），随后 `LocalBye`/`RemoteBye` 并正常退出；后续新 TLS 连接在仅信任 cert-B 的客户端上验证到 cert-B；同一进程上的仅信任旧 cert-A 的新连接验证失败（`self signed certificate`）。历史上 Contact 修正前（TLS-mode master-profile Contact 指向 UDP 端口）的 A/B reload 记录已 superseded，不作为 full TLS in-flight active-call 证据。该新增证据仍为窄范围 testbed 证据，不等于 runtime 平台绑定、外部 S-SBC/operator PKI/mTLS、双证书重叠窗口/热轮换验收。reSIProcate 上游已提供 `SipStack::reloadCertificates()`，但当前仍**未完成**平台 SIP transport binding/runtime adapter、TLS/peer-policy 运行时接线、外部 S-SBC 集成及双证书重叠窗口与热轮换验收；REQ-S-2/3（含 REQ-S-3）仍未验收。**M6 工程关门（2026-10-05）**：D8→REQ-NF-15；dev-host O1 正式批次见 [`m6-o1-measurement-report-2026-10-05.md`](acceptance/m6-o1-measurement-report-2026-10-05.md)（**非**对外 O1/SLA）。维护者 M6 里程碑签收仍 open。HPA 阈值、D3、M7 真 SIP 按 §4.4.3。**不**等于 `test-plan` 全 REQ 绿 —— F-13、F-15 真 AS、主叫/正则 v1.1 等见 **§5.4 补测**。证据门槛仍为 `make gate` + 维护者环境 PG integration（**origin CI 全绿非 M4 硬门禁**）。 |
| 版本称呼 | **没有 v1 / v1.1 定义（2026-10-07，维护者）**。产品版本号只看根目录 `VERSION`。其他文档里的「v1」「v1.1」不是发行版本，不能当作范围依据。要定义，须写在本文并经维护者确认 |
| 设计基线 | 已确认（`architecture/新系统整体架构.md`，决策 1–19） |
| 卡住后续里程碑的未决项 | §5（含 D11：REQ-F-4 SDP 原始 body 字节恒等的线上证明） |
| POC 代码的迁移 | 刻意推迟到 M1–M3，且由 [`migration/triage.md`](migration/triage.md) 把关 |
| M1 完成日期 | 2026-09-28（AI agent 代办；维护者签字待补，见 `docs/reviews/m1-exit-review.md`） |

**当前 config-service PostgreSQL integration 证据（2026-10-03）**：在与此前相同的本地 PostgreSQL 12.22（`wal_level=replica`）上，当前 API/bootstrap changes 后重跑完整 integration marker suite：**122 passed, 3 skipped, 432 deselected, 5 warnings**。3 个 publication DDL tests 因要求 `wal_level=logical` 而跳过。此为本地结果，未运行 CI，PG16 未测；该 suite 不证明 runtime factory 使用 DB-backed roles 的部署路径、生产 HTTPS ingress 或 browser workflow。它更新当前 integration evidence，不改写 M4b-6b 阶段历史快照中的 404 deselected，也不改变 M4b/M4、REQ acceptance 或 make-gate blocker。

上方当前状态摘要中所称的历史 PG12.22 integration，仅指 M4b-6b 阶段的 **404 deselected** 快照；当前结果为本段的 **432 deselected**。`cur` 上直接 `make gate` 已于 2026-10-03 通过；这不构成 M4/M4b/REQ acceptance。

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
| 4 | **O1（容量目标）有自己独立的研究阶段。** 这里不假设它，它也不阻塞骨架；HPA 阈值要在实测之后才定。 |

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

里程碑通常顺序推进。每个都以自己的完成定义收尾；上一个没签字，下一个不开始。维护者于 2026-10-03 授权在 `callload` 并行启动 M6 harness 工程工作；这是并行推进的窄范围例外，不改变其他里程碑的顺序门禁。

**callload → master（2026-10-06）**

| 项 | 记录 |
|---|---|
| 状态 | **已合入** — `master` @ `139d299`（2026-10-06，squash；**无** workflow 变更）；详见 [`handoff/2026-10-06-callload-merge-to-master.md`](handoff/2026-10-06-callload-merge-to-master.md) |
| 合入后入口 | **M8 发布候选**（[`handoff/2026-10-06-m8-release-candidate-plan.md`](handoff/2026-10-06-m8-release-candidate-plan.md)；工程 inventory：[`handoff/2026-10-05-milestones-engineering-complete.md`](handoff/2026-10-05-milestones-engineering-complete.md)）；**不**自动闭合 M2/M6/M7 维护者签收 |
| Demo 口径 | 故事 C 仍受 F10 约束（[`pre-m8-demo-review-plan.md`](handoff/pre-m8-demo-review-plan.md)） |

| # | 里程碑 | 产出 | 状态 | 门禁 |
|---|---|---|---|---|
| **M0** | 仓库骨架 | 本结构、守卫、ADR 注册表、CI | **已完成（维护者授权代签）** | §3，外加维护者签字 |
| **M1** | 甄别与行为基线 | 冻结 POC commit；抓取消息样例与 trace；确认或推翻 `migration/triage.md` 里每个裁决。**无产品代码。** | **已完成（2026-09-28；门禁裁决见 §4.1）** | 每个文件都有一个带证据的裁决；基线已抓取且可复现 |
| **M2** | 内核 | `platform/`：进程壳、`decide()` 缝、缝后面的 `RedisStateStore`、TLS transport、非阻塞导出的 OTel 三信号、内部 API 契约、feature 开关 seam | **工程完成（2026-10-05），M8 验收：** D3 Sentinel **客户端**接线、产品 `_resip_runtime`、TCP；见 [`m2-milestone-engineering-complete-adjudication-2026-10-05.md`](reviews/m2-milestone-engineering-complete-adjudication-2026-10-05.md)。**非** 维护者签收 / 全 REQ-S 验收 | 内核守卫绿；能在其上构建用例而不碰 sippy。**不含** Helm 部署 PG/Redis（那是 **M5 / D12**，见 §4.6） |
| **M3** | 应用 | `apps/translation` 与 `apps/anti-fraud`；决策模块先做 TDD | **已完成（2026-09-28；门禁裁决见 docs/reviews/m3-gate-review.md）** | 契约用例集对两者都重放绿 |
| **M4a** | 控制面后端与访问策略 | `services/config-service` 配置治理，以及 `services/console` 的纯访问策略 / 审计判定 | **已交付（2026-09-28）** | 纳入 **M4 工程关门**（§4.3） |
| **M4b** | 运维控制台 UI（强制） | M4 裁决定义：被叫+前缀、审批、compose HTTPS、fleet、M4b-8 浏览器证据 | **工程关门（2026-10-04）** | 见 §4.3；补测 §5.4；**不**等于 `test-plan` 全 REQ 绿。7.2d → M5。 |
| **M5** | 运维 | Helm chart、自定义指标 HPA、缩容保护控制器、draining / ISSU、告警规则集、控制面集群部署证明（含 **7.2d**）；**D12** 集群内 PG/Redis（ADR-0026） | **工程关门（2026-10-04，维护者授权代签）** | 评审 [`m5-closure-adjudication-2026-10-04.md`](reviews/m5-closure-adjudication-2026-10-04.md)；HPA/O1 → **M6** |
| **M6** | **容量研究** | 真实 socket 压测 harness；测出 CPS、并发会话、建立时延 —— 按栈分别 | **工程完成（2026-10-05），M8 验收：** D8→REQ-NF-15；O1 dev-host 正式批次 + 报告；见 [`m6-engineering-complete-adjudication-2026-10-05.md`](reviews/m6-engineering-complete-adjudication-2026-10-05.md)。**非** O1 目标发布/维护者签收 | 产出 O1 的答案；在真实栈正式测量跑起来之前不假设任何目标 |
| **M7** | 生产 SIP 集成与验收 | Python 产品决策模块接入 reSIProcate DUM/产品 CallController；完成协议行为和恢复验收 | **工程完成（2026-10-05），M8 验收：** E1 S1–S4 contract、D9 FORWARD、D10 checkpoint shell、D11 SDP 工程测试；见 [`handoff/2026-10-05-milestones-engineering-complete.md`](handoff/2026-10-05-milestones-engineering-complete.md)、[`m7-milestone-engineering-complete-adjudication-2026-10-05.md`](reviews/m7-milestone-engineering-complete-adjudication-2026-10-05.md)。**非** REQ-NF-1/E1 全量签收 | REQ-NF-1、operator PKI、维护者签收 → **M8** |
| **M7.1** | 测试模拟平台 | K8s 独立 namespace 的 IMS 仿真网：仿真 S-SBC、UDP/TCP/TLS、测试 UI、可配置呼叫类型与负载的 call load。用于 demo（步骤在本里程碑完成后再重评）。**不是** §5.2 D10 清单里已经完成的「M7.1 产品恢复接入」切片 | **工程关门（2026-10-07）** — [`handoff/2026-10-07-m7.1-sim-platform-plan.md`](handoff/2026-10-07-m7.1-sim-platform-plan.md) §11，证据 [`acceptance/m71-sim-platform-evidence.md`](acceptance/m71-sim-platform-evidence.md)。测试 CA 不签运营商 PKI。demo 重评与发布镜像 SIP 监听不在本关门内 | 编号、第一版呼叫类型、无 Kamailio、静态 UI、chart 与生产分开已拍板 |
| **M8** | 发布候选 | 带证据的验收运行、文档链完整、统一产品版本 | **RC 产物就绪；退出签字仍搁置（2026-10-07）**。M7.1 已工程关门。仍待 Close 前限制解除后再 revisit [`handoff/2026-10-07-m8-next-step-plan.md`](handoff/2026-10-07-m8-next-step-plan.md)。原状态：RC就绪、待维护者退出签字（2026-10-06） | 逐条验收报告 + M1/M2/M6/M7 维护者退出 |

**M6 状态更新（2026-10-05）**：**M6 工程关门**（[`m6-engineering-complete-adjudication-2026-10-05.md`](reviews/m6-engineering-complete-adjudication-2026-10-05.md)）：REQ-NF-15 关闭 **D8**；`m6-o1-formal-report.sh` 在 dev host 完成 30s/60s×cps10/20 产品路径批次，报告 [`m6-o1-measurement-report-2026-10-05.md`](acceptance/m6-o1-measurement-report-2026-10-05.md)。**不等于**对外 O1 目标发布、HPA 填值或 **M6 维护者里程碑签收**。先行 smoke/micro/60s 证据仍见 [`m6-product-60s-review-2026-10-05.md`](reviews/m6-product-60s-review-2026-10-05.md)。M7 工程尾项见 [`handoff/2026-10-05-m7-engineering-complete.md`](handoff/2026-10-05-m7-engineering-complete.md)。

**M4b-7.2 status clarification（2026-10-03）**：7.2c 含 config-service image recipe、默认关闭的 Helm workload/Ingress wiring；owner-only `as-config-migrate` 是新增的代码级 setup slice，要求 DBA 预先 provision roles，且不会创建/修改角色。Migration 与 bootstrap owner DSN 均是手动操作，不进入 web Pod。Helm render、镜像构建、真实集群、HTTPS、trusted-proxy 与 browser proof 仍归属 7.2d，保持 OPEN。Ingress 使用固定 redirect annotations，但真实 controller 必须保留默认 `nginx.ingress.kubernetes.io` annotation prefix，且 `no-tls-redirect-locations` 不得豁免 `/`；chart 本身不能配置这些 controller-level prerequisites。Helm lint/template 与 Docker image build 未验证；当前无 Helm render、真实集群或浏览器部署证据，不代表 M4b/M4 或 REQ acceptance。

**M4b implementation checklist（按顺序；M4 工程关门后仍 OPEN 仅：7.2d→M5、7.4→§5.4）：**

- [x] M4b-1 静态预览：四视图、本地 fixture、当前页面内存状态；不是验收证据。
- [x] M4b-2 管理规则 schema（本步骤）：config-service immutable management-plane rule model 与 REQ-F-12 单元测试。
- [x] M4b-3 durable PostgreSQL change-order journal（integration 在临时 PostgreSQL 12.22 上 6 passed；PG16 compatibility 为非阻塞跟进，不代表部署验收）。
- [x] M4b-4 durable PostgreSQL 管理规则持久化（在 PostgreSQL 12.22 测试通过；PG16 compatibility 为非阻塞 follow-up；[工程评审](reviews/m4b-4-managed-rule-store-review-2026-10-01.md)）。
- [x] M4b-5-1 identity/permission-gated read-only API：四个 managed-rule/change-order GET routes、schema-versioned response models、path validation 与 error mapping；28 个 API tests 通过；[工程评审](reviews/m4b-5-1-read-api-review-2026-10-01.md)。仅为工程切片，不代表 auth provider/session integration、M4b-5 完成或 UI 验收。
- [x] M4b-5-2a ChangeOrder schema-v2 journal snapshot 携带 typed ManagedRule proposal；兼容读取 schema-v1；active ManagedRuleStore 不写入、不改变。
- [x] M4b-5-2b identity/permission-gated ChangeOrder journal write API（注入 identity/permission callbacks；无真实 auth provider/session integration）：draft / submit / approve / reject，identity、权限、timestamp 与 ID generation 注入；submit / approve 权限分离、禁止 submitter 自批、拒绝理由必填、revision CAS、validation/error mapping；48 个 focused API tests 通过，独立评审无发现（维护者签字已记录 2026-10-04）。仅持久化 ChangeOrder snapshots，不改 active ManagedRuleStore、不分发或应用 ConfigBundle、不实现跨 store atomicity；该证据不是 M4b/M4 acceptance 或 REQ acceptance。
- [x] M4b-5-2c APPLIED 时共享 PostgreSQL transaction 协调：在同一 injected connection 上应用 typed CREATE/UPDATE/DELETE proposal，并追加 ChangeOrder APPLIED snapshot/head；调用方须提供专用、空闲且在调用期间独占的连接，不得与无关操作并发共享；PG12.22 integration coverage 通过，PG16 compatibility 为非阻塞 follow-up。仅是单 PostgreSQL transaction code slice，不代表 global/distributed atomicity、实际 distribution result wiring、验收或 M4b 完成。
- [x] M4b-5-2d1 durable PostgreSQL distribution journal：以 append-only immutable snapshots 持久化 batch-reported outcomes 与 observed status，并用 revision CAS 保证历史；PG12.22 focused integration 验证。unit 51 passed、PG integration 8 passed；[工程评审](reviews/m4b-5-2d1-distribution-journal-review-2026-10-02.md)。此 slice 不发送 AS instance 通知、不证明 fleet delivery、不激活规则或 ChangeOrder，也不是 M4b acceptance。
- [x] M4b-5-2d2 distribution API/report-to-activation engineering slice：从 APPROVED 开始分发，读取 observed status，接收当前 batch bool reports，部分健康推进、异常自动 rollback、成功完成后调用 activation coordinator，并提供受状态门控的 apply/manual rollback。使用注入的 permission seam，不发送 AS 通知、不证明加载版本或真实健康；Distribution completion 与 ManagedRule/ChangeOrder APPLIED 是两个事务。Focused API/PostgreSQL tests 79 passed，config-service integration 61 passed；最新本地 `make gate` 641 passed、2 skipped、67 deselected；独立评审无 actionable findings，维护者签字已记录（2026-10-04）。仅为工程切片，不代表 M4b/M4 acceptance 或 REQ acceptance，详见 [`acceptance/report.md`](acceptance/report.md) 与 [review](reviews/m4b-5-2d2-distribution-api-review-2026-10-02.md)。
- [x] M4b-6a 角色 / 密码身份验证与 session integration：基于 [ADR-0024](architecture/adr/0024-console-password-sessions.md)（accepted 2026-10-03），实现 fail-closed session auth primary path、保留 callback compatibility、user management、bootstrap CLI、HTTPS login、Host cookies 与写请求 CSRF。Focused API/auth/store tests **116 passed**；config-service integration **85 passed, 319 deselected**（临时 PostgreSQL 12.22）；M4b-6a 阶段当时的本地 `make gate` 快照：Ruff format 220 files already formatted、Ruff clean、mypy 44 source files、`unit or contract` **680 passed, 2 skipped, 91 deselected**。独立 reviewer 修复后无剩余具体发现；本地、未运行 CI；PG16、deployed trusted proxy、DB least privilege、rate limiting、durable audit、login UI 均未验证/未实现。此为交付的 engineering slice，不构成 REQ-S-4/M4b/M4 acceptance；详见 [`acceptance/report.md`](acceptance/report.md) 与 [review](reviews/m4b-6a-auth-session-review-2026-10-02.md)。
- [x] M4b-6b append-only persistent audit integration：PostgresAuditStore 与 API wiring 覆盖 allowed/denied outcomes、before/after snapshots、request-level domain-write/audit transaction 与 internal API routes；专用 schema/owner setup、allow-listed catalog 和 runtime-role privileges。Affected workflow matrix **264 passed, 3 skipped, 15 warnings**；API/audit catchall **89 passed, 15 warnings**；PG12.22 config-service integration **122 passed, 3 skipped, 404 deselected**（3 publication tests 因 `wal_level=replica` 跳过）；本地 `make gate` **767 passed, 2 skipped, 131 deselected**。最终集成评审修复后无 actionable findings；维护者签字已记录（2026-10-04）。仅为 engineering slice，不是 REQ-S-4/M4b/M4 acceptance；详见 [`acceptance/report.md`](acceptance/report.md) 和 [6b review](reviews/m4b-6b-audit-integration-review-2026-10-02.md)。
- [x] **M4b-7.1 Live read/session shell（engineering slice only）**：same-origin `/internal/v1` session restore/login/logout（logout 带 CSRF）、managed-rule/change-order live reads；`?preview=1` 保留本地 fixtures，live mode 不回退 fixtures；trace/operations 明确显示 unavailable。此项不构成验收。
- [x] **M4b-7.2a Same-origin ASGI static asset serving/package（engineering slice only）**：`create_app` 在 `/internal/v1` routers 之后从 `/` 提供 console assets；源码运行时 fallback 到 `services/console/web`，as-console wheel 包含 `index.html`、`console.js`、`console.css`。API TestClient 与 wheel 内容验证通过；这不是 acceptance，也不证明 production deployment。
- [x] **M4b-7.2b Config-service runtime factory/CLI（code-level engineering slice only）**：提供显式 ASGI factory 与 `as-config-service` Uvicorn factory-mode CLI；runtime 使用 `AS_CONFIG_DSN`、`AS_CONFIG_RUNTIME_ROLE`、`AS_AUDIT_RESOURCE_HMAC_KEY_B64`，单个 PostgreSQL 连接先 `SET ROLE`，再供所有 stores 共用，依赖预配置 runtime role/grants，startup 不执行 schema/migration/provisioning。Bootstrap CLI 单独要求 `AS_CONFIG_OWNER_DSN` 并共享 `AS_CONFIG_SCHEMA`；owner DSN 不属于 runtime Deployment。Focused runtime tests 覆盖配置、连接顺序与失败关闭；不构成部署或 acceptance 证据。
- [x] **M4b-7.2c Config-service image and Helm control-plane wiring（engineering slice only）**：独立 config-service image 包含 `as-config-service` runtime、`as-platform` direct workspace dependency 与 console assets；Helm 提供默认关闭的 Deployment、ClusterIP Service、可选 ingress-nginx 同源 Ingress 模板，并固定 redirect/force-HTTPS annotations。Deployment 只引用外部 runtime Secret 的 `AS_CONFIG_DSN` 与 audit key，使用预先 provisioned runtime role，不执行 DDL/provisioning；bootstrap owner DSN 不进入 runtime Secret。仅为模板 wiring；Helm render、镜像构建、集群 HTTPS、trusted-proxy 或 browser proof 均未验证，也不代表 acceptance。上述实际验证留在 7.2d。
- [x] **M4b-7.2c2 Owner-only database setup（engineering slice only）**：新增 `as-config-migrate`，通过 `AS_CONFIG_OWNER_DSN` 建立/验证非 public、独立的 `as_config` schema，调用 managed-rule/change-order/distribution/auth schema setup 与 `PostgresAuditStore.ensure_schema(runtime_role)`，再撤销 `PUBLIC`/runtime 的既有 schema/table/column 权限并只授予 runtime 所需权限。角色必须由 DBA 预先创建；migration 不创建/修改角色、不 `SET ROLE`。Runtime 与 bootstrap schema 默认对齐 `as_config`，web startup 仍无 DDL。Focused migration/runtime/bootstrap unit tests **37 passed**；不构成 DB deployment、Helm render、M4b/M4 或 REQ acceptance。
- [x] **M4b-7.2d HTTPS ingress/trusted-proxy（M5，2026-10-04）**：runbook 1–6；`make m5-7.2d-evidence`（L7 308/HTTPS 200 + Playwright 登录）；日志 `artifacts/m5/<date>/7.2d-evidence.log`。**不**等于维护者签字或 REQ 验收。
- [x] **M4b-7.3a Live decisions on existing ChangeOrders（engineering slice only）**：live table/modal 支持 draft creator 提交既有 draft，以及由不同 approver 批准或拒绝 submitted order；API 禁止 creator 自拒绝。仅是现有 ChangeOrder 的 submit/approve/reject workflow，不提供规则 CRUD/create/edit/write，也不是 M4b/M4 或 REQ acceptance；route-mocked browser checks 与 focused API regression evidence 见 [`acceptance/report.md`](acceptance/report.md)。
- [x] **M4b-7.3b ManagedRule write/approval integration（M4 被叫+前缀）**：`runtime_bundle`、managed-rules API、live console、`test_postgres_managed_rule_pipeline_integration.py`；compose PG integration 与 M4b-8 浏览器证据（2026-10-03/04）。不等同全 REQ 验收。
- [ ] **M4b-7.4 Live Call-ID trace**：**不纳入 M4 工程关门**；补测见 **§5.4**（REQ-F-13）。
- [x] **M4b-7.5 distribution/health（M4 工程切片）**：`as_instances`、notify、testbed health probe、Operations fleet UI、`test_fleet_api.py`。**完整 AS 栈**补测见 **§5.4**。
- [x] **M4b-7.6 browser workflow（M4 裁决定义链）**：distribution modal UI + Playwright 被叫+前缀 propose→审批→distribution start（`artifacts/m4b-8/2026-10-03/`）。F-13 trace 不适用；全 REQ 链见 §5.4。
- [x] **M4b-8 dev HTTPS same-origin evidence**：runbook + 脱敏 artifact；维护者签字 2026-10-04。**不**宣称 REQ-F-12/13/14/15 与 REQ-S-4 全绿；BLOCKED/N/A 见 runbook。

主叫/正则为 **v1.1**（§5.4）。**M4 工程关门**见 §4.3；**REQ 级整体验收**未声明。

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

M6 是一个带决策的研究里程碑，不是对某个数字的承诺。容量研究仍按原顺序留在 M6，并使用真实 socket；流量模型与负载生成器决策也留在 M6，不纳入 M4b。**2026-10-05：** M6 **工程关门**（harness + D8 + dev-host O1 正式批次报告）；维护者 **M6 里程碑签收**与对外 O1 **目标**仍 open。饱和点、集群多副本与 HPA 阈值不在本关门范围。

### 4.2 M4 关门裁决（2026-10-03）

维护者 grill 会话确认的关门边界已写入 [`reviews/m4-closure-adjudication-2026-10-03.md`](reviews/m4-closure-adjudication-2026-10-03.md)。摘要如下（**不宣称 M4/M4b/REQ 已通过**）：

| 项 | 裁决 |
|---|---|
| 7.2d 生产 ingress/trusted-proxy | 与 **M5** 集群验收捆绑；**非** M4 硬门禁 |
| 7.5 / REQ-F-15 | **M4**：PG 实例 inventory 表 + 出站 notify + testbed health；集成后 **AS 全栈补测** |
| M4 浏览器 HTTPS | compose / 自签 / 本地反代同源证据，支撑 **M4b-8** |
| REQ-F-13 / 7.4 | **M4 延期**；集成栈完成后补测 |
| 规则匹配轴 / M4 控制台范围 | **已裁决（2026-10-03）**：被叫匹配（REQ-F-6/F-7）；M4 **被叫+前缀**；主叫/正则 **v1.1**。见 [`reviews/m4-req-calling-regex-lossless-adjudication-2026-10-03.md`](reviews/m4-req-calling-regex-lossless-adjudication-2026-10-03.md) |
| ADR-0024 | **Accepted**（2026-10-03，[`review`](reviews/adr-0024-console-password-sessions-review-2026-10-02.md)）；REQ-S-4/M4b 验收仍独立 |
| 证据 git | 可在 `cur` **命名 commit** 上采证；合并与签字可同周 |
| CI | **`make gate` + 维护者环境 PG integration** 足够；**origin CI 全绿非 M4 硬门禁** |
| PostgreSQL | M4 证据 **12.22**；**PG16** 非阻塞跟进 |
| M4b-8 | 工程/AI 跑步骤与脱敏 artifact；维护者审阅签字 |

**M4 工程证据维护者签字**：M4b 切片 reviews + M4b-8 artifacts/runbook **已记录 2026-10-04**（chat 授权代签）；**不**等于 REQ 级整体验收。补测与 v1.1 见 **§5.4**；7.2d 见 **M5**（未启动前不改 M5 表内前置表述）。

### 4.3 M4 工程关门（2026-10-04）

| 项 | 记录 |
|---|---|
| 裁决 | [`m4-closure-adjudication-2026-10-03.md`](reviews/m4-closure-adjudication-2026-10-03.md) |
| 证据 commit | `1bca9eee`（m4 close）、`643bdb6`（m4 approved），分支 `cur` |
| 范围 | M4b 强制控制台 + 被叫+前缀 + compose 同源 HTTPS + M4b-8 材料 |
| 明确不含 | `test-plan` 全 REQ 绿；F-13；F-15 真 AS；主叫/正则 v1.1；7.2d 生产 ingress |

### 4.4 M5 工作计划（2026-10-04；分支 `cur`）

**前提**：M4 工程关门（§4.3）已满足；里程碑表「M4b 通过后」在流程语义上指同一前提。

**关门条件（不变）**：在**真实 Kubernetes 集群**上取得可复现证据——(1) 滚动升级不掉在途呼叫（按 ADR-0009 draining 语义观测）；(2) 缩容不掉在途呼叫（ADR-0010 判据 + draining）；(3) **M4b-7.2d** ingress/trusted-proxy 与浏览器/客户端 HTTPS 行为。HPA **启用**与容量类告警依赖 O1/M6，**不**阻塞 M5 工程关门（见 §4.4.3）。

#### 4.4.1 代码核查快照（2026-10-04；非仅文档）

| 能力 | 状态 | 仓库事实 |
|---|---|---|
| Helm AS 工作负载 | **已交付** | `deploy/helm/`；`helm lint` / 默认 `helm template` → 7 对象；`autoscaling.enabled=true` 且无 `minReplicas` → **按设计 fail** |
| HPA / PDB 模板 | **已交付** | `hpa.yaml` `required` 守卫；默认关闭；无 O1 数字 |
| 告警规则 | **已交付** | `deploy/alerts/as-alerts.yaml`；比例/状态量，无 CPS/并发绝对值 |
| ISSU / draining（模板 + 进程壳） | **部分** | Chart：`preStop` + `terminationGracePeriodSeconds`；`ProcessShell` + SIGTERM 单测；**运行时 `active_calls` 恒为 0**（`as_platform.__main__`） |
| 缩容保护判据（ADR-0010） | **已交付（运维层）** | `plan_scale_down` + unit；`AS_DOWNSCALE_GUARD_*` 已由 `platform/__main__` 读取；无 in-cluster actuator（ADR 允许运维脚本） |
| `as_active_calls` 指标 seam | **M5 已接线** | Helm metrics 路径 + 模拟计数；真 SIP 计数 **M7** |
| Readiness vs draining | **已交付** | Deployment `httpGet` `/health/ready`；draining → 503 |
| PostgreSQL `VersionStore` runtime | **已交付** | `runtime.py` → `PostgresVersionStore`；activation/API 使用；integration 面大于 2026-09 `report.md` M5 段快照 |
| config-service Helm | **模板已交付** | 默认关闭；**未**纳入 CI 渲染矩阵；7.2d 未 cluster 证明 |
| 平台 / config-service 镜像 | **部分** | `deploy/docker/Dockerfile` 历史构建证据；config-service 镜像 recipe 在 M4b-7.2c；**须在 M5 重跑 build** |
| 真实集群 ISSU / 缩容 | **kind 已证据（2026-10-04）** | `m5-issu-scale-evidence.sh` + `issu-scale-evidence.log`（模拟 `active_calls`）；生产集群采证仍客户环境 |
| CI chart 回归 | **已交付（M5-0c）** | CI ① `chart-check`；本地 `make chart-check` |

#### 4.4.2 已提前交付（2026-09-28–30；勾选表示工件在库，不等于 M5 关门）

- [x] M5-a Helm chart 骨架与 values 契约（ADR-0013；[评审](reviews/m5-a-helm-chart-review-2026-10-04.md) + [H1–H9](reviews/m5-helm-alerts-review.md)）
- [x] M5-b 告警规则工件（REQ-NF-14；[评审](reviews/m5-b-alerts-review-2026-10-04.md)）
- [x] M5-c `plan_scale_down` 缩容保护纯函数 + unit（ADR-0010）
- [x] M5-d `MetricsRegistry` / `CallMetrics` / `as_active_calls` 命名契约（ADR-0005；与 `deploy/alerts/README.md` 对齐）
- [x] M5-e `PostgresVersionStore` + config-service PG integration 用例（治理闭环；runtime factory 已接线）
- [x] M5-f 平台容器镜像 + 容器内 SIGTERM draining smoke（`report.md` M5 容器镜像段）

#### 4.4.3 明确后置（不阻塞 §4.5 M5 工程关门）

| 项 | 归属 | 说明 |
|---|---|---|
| HPA `minReplicas` / `maxReplicas` / 自定义 `as_active_calls` 阈值 | **M6 后填 values** | O1 实测前禁止猜测（AGENT.md §2、§6） |
| 容量类告警（CPS / 并发上限） | **M6 后** | `as-alerts.yaml` 已注明；新增 `as.capacity` 组 |
| D3 Redis Sentinel / 脑裂幂等 | **M2 / O5** | 不纳入 M5 首包除非维护者改计划 |
| 真实 SIP 负载下的「不掉呼叫」 | **M7 加强** | M5 可用注入/模拟 `active_calls` 或 testbed 占位证明 draining/缩容**机制**；产品路径 E1 仍属 M7 |

#### 4.4.4 M5 implementation checklist（按顺序）

**阶段 0 — 可重复基线**

- [x] **M5-0a** `make gate` 全绿（2026-10-04：`m4b-8-seed-users.py` `main` docstring）
- [x] **M5-0b** integration 可重复：`make test-integration-compose` → **142 passed, 3 skipped**（compose PG 12.22，`wal_level=replica` 跳过 3 条 publication 用例）
- [x] **M5-0c** **chart-check**：`make chart-check` / `deploy/helm/scripts/chart-check.sh`；CI ① fast 已纳入

**阶段 1 — 部署工件与 7.2d**

- [x] **M5-1a** 镜像 `as-platform:m5`、`as-config-service:m5`（digest 见 `artifacts/m5/2026-10-04/M5-evidence-summary.md`）
- [x] **M5-1b** kind `as-m5` + Helm release `as`（translation/anti-fraud Running）
- [x] **M5-1c** Ingress 模板/对象（[评审](reviews/m5-1c-ingress-template-review-2026-10-04.md)）；关门 4–5 → **M5-7.2d**
- [x] **M5-1d** config-service Ready + PG（[评审](reviews/m5-1d-config-pg-review-2026-10-04.md)）：kind 默认 **bundled**（§4.6）或 compose `:55432`；生产 Chart 默认不内建库

**阶段 2 — draining / 缩容运维链（可无真实 SIP）**

- [x] **M5-2a** `GET :8080/metrics` → `as_active_calls{pod,use_case}`；周期 `emit_snapshot` 当 OTLP 配置时
- [x] **M5-2b** HTTP readiness `/health/ready` → 503 when draining（Helm `httpGet`；单测 `test_health_server.py`）
- [x] **M5-2c** `load_downscale_guard_config()` 在 `as_platform.__main__` 读取 `AS_DOWNSCALE_GUARD_*`
- [x] **M5-2d** [`m5-downscale-runbook.md`](acceptance/m5-downscale-runbook.md)

**阶段 3 — M5 关门证据**

- [x] **M5-3a** `kubectl rollout restart` anti-fraud — success（kind log）
- [x] **M5-3b** scale to 1 + `plan_scale_down` 脚本断言（`m5-rollout-scale.sh`）
- [x] **M5-3c** §4.5 撰写；`m5-helm-alerts-review.md` 工程关门注记；**维护者签字不在此步**（须 7.2d 全项 + 维护者自评）

**跟踪**：M4b checklist **M4b-7.2d** 与 M5 **M5-1c 切片** 同步；**签字前**须勾满 7.2d runbook（含 4–5），不得用 port-forward 顶替 L7 证明。

### 4.5 M5 工程关门（2026-10-04）

| 项 | 记录 |
|---|---|
| 证据摘要 | [`acceptance/m5-engineering-closure-2026-10-04.md`](acceptance/m5-engineering-closure-2026-10-04.md)；脚本 `deploy/kind/m5-*.sh` |
| 门禁 | `make gate`（863+ unit/contract）；`make chart-check`；`make test-integration-compose` |
| 范围 | §4.4.2 + §4.4.4 全部勾选；平台 health/metrics/draining；kind 滚动/缩容 |
| 明确不含 | HPA `minReplicas`/自定义阈值（**→ M6**）；D3 Sentinel（**→ M2/O5**）；M7 真 SIP 不掉呼叫（**→ M7**） |
| kind PG / ingress | **M5-1d**：compose PG + 脚本；维护者签字前跑 `make m5-kind-verify` |
| 维护者签字 | **Approved 2026-10-04**（chat 授权 AI agent 代签）；见 [裁决](reviews/m5-closure-adjudication-2026-10-04.md)；**不**等于 REQ 验收 |

### 4.6 M5 补交付 — D12 / ADR-0026（2026-10-04 起；**不是 M2**）

**时间线（避免与 M2 混淆）**

| 阶段 | 发生了什么 |
|------|------------|
| **M5 原关门（§4.5）** | kind 上 3 个 AS/config Pod；Chart **不内建** PG/Redis；7.2d、draining、metrics |
| **M5 验收复盘** | 发现 config-service 需 **真实 PG**（占位 DSN → CrashLoop）；compose 宿主机 `:55432` 过渡（**M5-1d**）；并讨论 IMS PG 不可用、Redis/PG 应在 **同 namespace** |
| **架构裁决** | [ADR-0026](architecture/adr/0026-in-cluster-state-stores-proposal.md) accepted：单 chart、`stateStores`、禁止 IMS PG |
| **工程补交付（本节）** | Helm `stateStores` 模板 + kind `M5_BUNDLED_STATE=1`；**不改变** M2 定义（M2 仍是 `RedisStateStore` **代码缝**，不是 Helm 装库） |

**与 M2 的分工**

| 主题 | 里程碑 |
|------|--------|
| `RedisStateStore` / `StateStore` 契约、进程外状态 **模型** | **M2**（已交付 seam + Sentinel **客户端**接线；HA 拓扑仍 **O5**） |
| Helm 在同一 namespace **渲染** PG+Redis、NetworkPolicy、kind 连线 | **M5 §4.6 / D12** |
| 产品 SIP 使用 Redis、checkpoint | **M7** / D10 |

**§4.6 checklist**

- [x] ADR-0026 accepted（单 chart 合并，拒绝双 release）
- [x] `deploy/helm/templates/state-*.yaml` + `values.stateStores` + `chart-check` bundled 矩阵
- [x] `m5-helm-install.sh` 默认 `M5_BUNDLED_STATE=1`（集群内 PG/Redis + AS 同 ns）
- [x] 生产 profile：`deploy/helm/values-onprem.example.yaml`；[`m5-state-stores-runbook.md`](acceptance/m5-state-stores-runbook.md)（migrate / 备份 / ISSU 分章）
- [x] ADR-0013 Amendment 段 + [`新系统整体架构.md`](architecture/新系统整体架构.md) §6.1 落点说明
- [x] **§4.6 关门复验**（2026-10-04）：`make gate` / `chart-check` / `test-integration-compose` 142 passed；kind `postgres-0`+`redis`+AS+**config-service Ready**；`as-config-migrate`；headless PG Service 修复；ingress 对象已渲染（kind admission webhook 见 runbook）
- [x] **§217①② + H10**（2026-10-04）：`make m5-issu-scale-evidence` → draining 503 + `plan_scale_down` 允许/拒绝路径；见 `m5-downscale-runbook.md`
- [x] **ADR-0026 生产轨（工程）**：`state-migrate-job.yaml` + `values-onprem` + runbook HA/PITR/migrate Job（Redis HA 仍 D3）
- [x] **M5 维护者签字**（2026-10-04；chat 授权代签；依据 task register + adjudication + [`m5-evidence-summary.md`](acceptance/m5-evidence-summary.md)）
- [x] **M5 工程评审**（2026-10-04）：[`m5-task-register-2026-10-04.md`](reviews/m5-task-register-2026-10-04.md) 逐项 review + 裁决

---

## 5. 未决项

### 5.1 从架构文档继承（§12.1）

| # | 条目 | 阻塞 | 解决所需 |
|---|---|---|---|
| O1 | 容量目标：CPS、并发会话、建立时延预算。**已有量级估计**（见 [`architecture/容量量级估算.md`](architecture/容量量级估算.md)）与 **dev-host 实测草稿**（[`acceptance/m6-o1-measurement-report-2026-10-05.md`](acceptance/m6-o1-measurement-report-2026-10-05.md)，非 SLA） | M7 集成容量验收、HPA 阈值（M5） | **维护者目标裁决仍 open**；C6 1s 峰值已在低 CPS 批次记录；C1–C5/C7 与饱和点待更高保真测量 |
| O2 | **已选定 reSIProcate C++**（ADR-0019 Accepted）；生产栈方向不变。DUM/controller 集成与 E1/E4/E5 仍未验证 | D9、D10、M7 | ADR-0019 的选型结论不代替集成或需求验收；K2 未解除 |
| O3 | reSIProcate 生产路径的 SIP 行为验收（E1，S1–S11） | M7 / M8 | native DUM S1/S4 smoke 不是产品 E1；完成集成 spike 后由产品 adapter 通过真实 socket probe 验证 |
| O4 | 呼叫轨迹保留期 | M4 | 客户合规要求 |
| O5 | 容灾等级：N+1（节点）还是 N+M（机架 / AZ） | M5 Redis 拓扑 | 客户 SLA |

### 5.2 搭骨架时新增

| # | 条目 | 阻塞 | 说明 |
|---|---|---|---|
| D1 | **Python 3.10 在 2026 年 10 月到达生命周期终点。** 产品锁 3.10 是因为那是 sippy 验证过的版本。 | 该日期之后的任何交付 | 尽早验证 sippy 在 3.11 / 3.12 上的行为；要么迁移，要么在 ADR 里把 EOL 运行时登记为已接受的 risk。这里不定。 |
| D2 | ~~同一用例的第二个语言实现放置位置~~ **已不适用**：当前产品决策模块保持 Python；reSIProcate 集成边界由 D9 spike 处理 | — | 不启动第二个业务实现；跨实现一致性仍按语言无关契约验证（ADR-0012） |
| D3 | Redis 客户端与 Sentinel 接线；脑裂窗口下的判决幂等 | **M2 客户端接线 resolved（2026-10-05）**；HA 拓扑 **O5**；幂等契约已有 | 风险 R5；[`m2-d3-sentinel-adjudication-2026-10-05.md`](reviews/m2-d3-sentinel-adjudication-2026-10-05.md) |
| D4 | ~~控制台前端形态：保留 vendored 单包、无构建步骤，还是接受一套工具链~~ **已裁决（2026-10-01）**：使用纯 HTML/CSS/JavaScript，不引入 bundler、build tool 或前端 runtime 依赖 | —（已解决） | 当前 console 尚无 HTTP/runtime 前端；无构建步骤适合简单的 on-premises 交付。M4b-1 只交付可直接打开的静态预览，不代表 M4b 后端、鉴权、持久化、workflow integration 或验收已完成 |
| D5 | 呼叫轨迹存储：PostgreSQL，还是独立的短保留存储 | M4 | 与 O4 相关 |
| D6 | testbed 是否必须在 v1 支持客户验收测试 | M8 | 架构文档把它推迟到 v1.1 |
| D7 | ~~未决~~ **已裁决（2026-09-28）**：粒度固定为号段 + 稳定哈希百分比，schema 与判定幂等见 [ADR-0021](architecture/adr/0021-runtime-override-granularity.md) | M4 | 与 ADR-0020 的分层门控相关，需在控制面设计前定 |
| D8 | ~~ADR-0014 PRD 追溯缺口~~ **已关闭（2026-10-05）**：[REQ-NF-15](requirements/req-nf-15-testbed-performance.md)；[`d8-req-nf-15-adjudication-2026-10-05.md`](reviews/d8-req-nf-15-adjudication-2026-10-05.md) | — | REQ-NF-15 **全量 test-plan 绿**与 M8 签收仍独立跟踪 |
| D9 | **已解决（M7 工程，2026-10-05）：** 产品 `_resip_runtime` adapter API（`on_invite` int / forward dict、FORWARD UAC、486 映射、CANCEL 协调）；见 [`platform/src/as_platform/sip/README.md`](../platform/src/as_platform/sip/README.md) | M8 E1 全量 / forking | Forking 与 final-response race 覆盖仍属 **M8 验收**；业务决策继续使用 Python |
| D10 | **工程已解决（2026-10-05）：** `SipStackService` establish → `CallCheckpointCommit` → Redis；进程壳 harness + recovery TU 切片。REQ-NF-1 **验收** checkbox仍 **M8 维护者**（K8s live baseline） | M8；REQ-NF-1 验收 | ACK-established-dialog BYE/Redis **正式签收**仍为硬要求；UAS 481 风险与 operator 环境见 test-plan。**不等于** mid-transaction recovery 扩展。 |
| D11 | **工程测试覆盖完成（2026-10-05）：** `test_req_f4_sdp_identity_integration.py` + D11 fixtures；产品 FORWARD 路径 offer 字节 compare | M8；REQ-F-4 **签收** | REQ-F-4 正式通过仍须 M8 review + 更广 corpus；不得单独宣称 REQ 绿 |
| D12 | **集群内治理 PG + 运行态 Redis**（**自 M5 kind 验收复盘引出**，非 M2） | **M5 §4.6**；O5 / **D3（仍归 M2 客户端缝）** | [ADR-0026](architecture/adr/0026-in-cluster-state-stores-proposal.md) **accepted**；Helm `stateStores` 骨架已落库；生产 HA/签字见 §4.6 checklist |

**D10 的 M7 阻塞 TODO（依赖顺序；全部完成并有验收证据前保持“不通过 / 未解决”）**：

- [x] **M7.1 产品恢复接入**（工程切片，2026-10-05）：`platform/native/resip_recovery/` + `RecoveryStackSession`；D10 **维护者签收仍 pending** — [`m7-1-recovery-tu-review-2026-10-05.md`](reviews/m7-1-recovery-tu-review-2026-10-05.md)。
- [x] **M7.2 非阻塞恢复读取**（工程切片，2026-10-05）：`recovery_coordinator.py` + 单测；D10 acceptance **pending** — [`m7-2-recovery-coordinator-review-2026-10-05.md`](reviews/m7-2-recovery-coordinator-review-2026-10-05.md)。
- [x] **M7.3 CallController context restoration**（工程切片，2026-10-05）：`restore_from_checkpoint` / `route_in_dialog_bye` — [`m7-3-call-controller-recovery-review-2026-10-05.md`](reviews/m7-3-call-controller-recovery-review-2026-10-05.md)。
- [x] **M7.4 owner 与提交安全**（工程切片，2026-10-05）：schema v2 + `CallCheckpointCommit` / `save_if_generation`（ADR-0023 注释）— [`m7-4-checkpoint-commit-review-2026-10-05.md`](reviews/m7-4-checkpoint-commit-review-2026-10-05.md)。
- [x] **M7.5 checkpoint 生命周期**（工程切片，2026-10-05）：`CallCheckpointLifecycle` — [`m7-5-checkpoint-lifecycle-review-2026-10-05.md`](reviews/m7-5-checkpoint-lifecycle-review-2026-10-05.md)。
- [x] **M7.6 D10 产品集成测试**（工程切片，2026-10-05）：`test_d10_product_recovery_integration.py`（**非** REQ-NF-1 / 全 D10 签收）— [`m7-6-d10-product-integration-review-2026-10-05.md`](reviews/m7-6-d10-product-integration-review-2026-10-05.md)、[`m7-d10-product-adjudication-2026-10-05.md`](reviews/m7-d10-product-adjudication-2026-10-05.md)。
- [x] **M7.7 进程壳 + REQ-NF-1 工程 harness**（工程切片，2026-10-05）：`SipStackService`、`test_d10_req_nf1_harness_integration.py`（**非** REQ-NF-1 / 全 D10 签收）— [`m7-process-shell-recovery-review-2026-10-05.md`](reviews/m7-process-shell-recovery-review-2026-10-05.md)、[`d10-req-nf1-harness-review-2026-10-05.md`](reviews/d10-req-nf1-harness-review-2026-10-05.md)、[`m7-d10-third-pass-review-2026-10-05.md`](reviews/m7-d10-third-pass-review-2026-10-05.md)。

本次 4 KiB extension payload、16 KiB checkpoint 与 30-day TTL 上限只是 payload / retention groundwork only，不实现上述恢复、提交或生命周期语义。此 TODO 序列仅覆盖当前 ACK-established-dialog baseline，不把 D10 扩展到崩溃时的 mid-transaction recovery；该可选未来范围须另行获得 requirement 与 test-plan 批准。

### 5.3 PM / AM / UM 产品管理能力缺口（需求待补）

以下是尚未完整需求化的产品能力缺口，不是 M4b 的隐含扩项；M4b 仅包含当前控制台的 REQ-S-4 基础鉴权与审计。

| 能力 | 已有部分能力 | 尚缺能力与下一步 |
|---|---|---|
| PM（Performance Management） | REQ-NF-13 提供 OTel metrics / traces / logs；M5 已有指标与告警规则工件 | 这些不是 PM 管理产品或工作流，也不代表已有 live dashboard。补充 PRD requirement 与验收标准后，可作为独立 feature 规划 |
| AM（Alarm Management） | REQ-NF-14 与 M5 告警规则集 | 尚无完整告警生命周期管理（ack / clear / suppress / history / operator workflows）。先补 PRD requirement 与验收标准，再单独规划 |
| UM（User Management） | M4b-6a 在 ADR-0024（accepted）下提供基础本地账号、角色、密码与 session engineering slice；M4b-6b 后续交付 durable audit API/store engineering slice。两者均不构成 REQ-S-4 acceptance，也不代表 M4b 完成 | UM 仍是独立缺口：尚无获批的完整 UM requirement / acceptance，覆盖完整 operator account lifecycle、UI/workflows、SSO / MFA、password recovery / lockout / session UX。继续在 base scope 之外单独规划；不并入或据此标记完成 M4b |

在上述需求与验收标准获批前，不把 PM / AM / UM 的未定义功能并入 M4b。

### 5.4 M4 后补测与 v1.1（不阻塞 §4.3 M4 工程关门）

以下在 M4 关门时**刻意后置**；在对应栈/里程碑就绪后再做，不回头阻塞 M4 工程签字。

| 项 | 计划归属 | 说明 |
|---|---|---|
| REQ-F-13 / M4b-7.4 Call-ID live trace | 信令/集成栈 + M7 前后 | 无 trace store/API；M4b-8 标 BLOCKED |
| REQ-F-15 **完整 AS 栈**（非 testbed notify/health） | M7 集成后补测 | M4 已交付 inventory + notify + testbed probe + 浏览器 distribution start |
| 主叫 / 正则规则（REQ-F-12 四维 UI） | **v1.1** | M4 live 仅被叫+前缀 |
| REQ-S-4 / `test-plan` §1.4 **正式全绿** | M8 或维护者单独签收 | 与 §4.3 工程关门分离 |
| PostgreSQL 16 | 非阻塞 follow-up | 证据基线 12.22 |
| M4b-7.2d 生产 ingress / trusted-proxy | **M5** | 见 §4.4.4 M5-1c / M4b checklist 7.2d |

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
