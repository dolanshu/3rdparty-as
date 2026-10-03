# 计划（Plan）— `3rdparty-as`

产品化的第三方 IMS Application Server。单租户、on-premises 交付，部署在运营商网络之外，
由 S-CSCF 经运营商的 S-SBC 触发。

设计基线是 [`architecture/新系统整体架构.md`](architecture/新系统整体架构.md)。
本文是建立在它之上的计划。

---

## 0. 本计划的状态

| | |
|---|---|
| 当前进行中的步骤 | **M4b —— 运维控制台 UI（强制）；M4b-7.1、7.2a–7.2c、7.3a 已交付为 engineering slices**，包括 owner-only `as-config-migrate` 手动 DB setup。关门裁决见 **§4.2（2026-10-03）**：7.2d 正式生产 ingress/trusted-proxy 证明并入 **M5**；M4 浏览器同源 HTTPS 可用 compose/自签/本地反代支撑 M4b-8。7.3b ManagedRule CRUD/lossless runtime bundle contract、7.4 trace（M4 延期）、7.5 实例 inventory/notify/testbed health（M4 范围）、7.6 full browser workflow 与 M4b-8 acceptance 仍开放。Focused migration/runtime/bootstrap tests **39 passed**。当前分支 `cur` 上 **`make gate` 绿**（2026-10-03）：Ruff format/check、mypy **48 sources clean**、`unit or contract` **838 passed, 2 skipped, 143 deselected, 11 warnings**。M4 证据门槛：本地 `make gate` + 维护者环境 PG integration 即可；**origin CI 全绿不是 M4 硬门禁**（验收报告须写明）。本次未运行 CI 或 Helm render/deployment；此前 Helm CLI/registry 限制仍适用。PG16 未测；M4b/M4 与所有 REQ acceptance 保持开放。ADR-0024 已于 2026-10-03 Accepted（见 [`adr-0024-console-password-sessions-review-2026-10-02.md`](reviews/adr-0024-console-password-sessions-review-2026-10-02.md)）。Owner/runtime DSN 分离、数据库角色预配置；HMAC key 外部提供且轮换会打断跨周期关联；敏感值检测仍要求 producer allow-list/redaction。较早 d2 slice 不证明 AS 通知、fleet delivery 或真实健康 attestation，Distribution completion 与 ManagedRule/ChangeOrder APPLIED 为两个 PostgreSQL transactions；详见 §4.2、§5.3 与 handoff） |
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

里程碑是顺序的。每个都以自己的完成定义收尾；上一个没签字，下一个不开始。

| # | 里程碑 | 产出 | 状态 | 门禁 |
|---|---|---|---|---|
| **M0** | 仓库骨架 | 本结构、守卫、ADR 注册表、CI | **已完成（维护者授权代签）** | §3，外加维护者签字 |
| **M1** | 甄别与行为基线 | 冻结 POC commit；抓取消息样例与 trace；确认或推翻 `migration/triage.md` 里每个裁决。**无产品代码。** | **已完成（2026-09-28；门禁裁决见 §4.1）** | 每个文件都有一个带证据的裁决；基线已抓取且可复现 |
| **M2** | 内核 | `platform/`：进程壳、`decide()` 缝、缝后面的 `RedisStateStore`、TLS transport、非阻塞导出的 OTel 三信号、内部 API 契约、feature 开关 seam | **M2a 已完成；M2b seam 已落（2026-09-28），栈绑定未开始** | 内核守卫绿；能在其上构建用例而不碰 sippy |
| **M3** | 应用 | `apps/translation` 与 `apps/anti-fraud`；决策模块先做 TDD | **已完成（2026-09-28；门禁裁决见 docs/reviews/m3-gate-review.md）** | 契约用例集对两者都重放绿 |
| **M4a** | 控制面后端与访问策略 | `services/config-service` 配置治理，以及 `services/console` 的纯访问策略 / 审计判定；console 仍是骨架，`access.py` 不含 HTTP、login、session、password 或 persistence 实现 | **后端 / 策略切片已交付（2026-09-28）；不代表整体 M4 完成** | 后端治理闭环与开关两态测试；整体 M4 还须通过 M4b |
| **M4b** | 运维控制台 UI（强制） | operator UI：按 REQ-F-12/13/14/15 提供规则 CRUD、审批队列、Call-ID 轨迹查询、灰度分发 / 回滚工作流；静态预览与管理规则 schema 已交付 | **M4b-7.1、7.2a–7.2c、7.3a 为已交付 engineering slices；7.2d、7.3b、7.4–7.6 与 M4b-8 仍 OPEN；M4b/M4 整体未验收** | 登录/session shell、ASGI static hosting/package、runtime factory/CLI、独立 config-service image、默认关闭的 Helm Deployment/ClusterIP Service/optional Ingress 与既有 ChangeOrder submit/approve/reject UI 已实现，但不等于验收。仍须完成真实 HTTPS ingress/trusted-proxy proof、ManagedRule create/edit/delete 与 lossless bundle compiler、Call-ID trace、AS inventory/notifier/真实 health 与 live distribution/rollback、full browser workflow，以及 [`acceptance/test-plan.md`](acceptance/test-plan.md) §1.4/§3 acceptance。ADR-0024 **accepted**（2026-10-03）；M4b/M4 与 REQ acceptance 均未通过。 |
| **M5** | 运维 | Helm chart、自定义指标 HPA、缩容保护控制器、draining / ISSU、告警规则集 | **工程工作已提前部分交付（2026-09-28–30：Helm / 告警 / 渲染校验 / 缩容保护 / PG 闭环 / 容器镜像）；正式阶段闭合 / 后续顺序受 M4b 把关；真实集群滚动升级与缩容验证仍未完成** | M4b 通过后，在真实集群验证滚动升级不掉呼叫、缩容不掉呼叫，方可关闭 M5 |
| **M6** | **容量研究** | 真实 socket 压测 harness；测出 CPS、并发会话、建立时延 —— 按栈分别 | 未开始 | 产出 O1 的答案；在这跑起来之前不假设任何目标 |
| **M7** | 生产 SIP 集成与验收 | Python 产品决策模块接入 reSIProcate DUM/产品 CallController；完成协议行为和恢复验收 | 未开始（仅有探索性证据；产品集成/验收未开始） | **受 D9、D10、D11、E1/E4/E5 把关。** REQ-NF-1 为硬验收要求；REQ-F-4 SDP 字节恒等须由完整产品路径验收；M6 容量测试仍须使用真实 socket |
| **M8** | 发布候选 | 带证据的验收运行、文档链完整、统一产品版本 | 未开始 | 逐条验收报告 |

**M4b-7.2 status clarification（2026-10-03）**：7.2c 含 config-service image recipe、默认关闭的 Helm workload/Ingress wiring；owner-only `as-config-migrate` 是新增的代码级 setup slice，要求 DBA 预先 provision roles，且不会创建/修改角色。Migration 与 bootstrap owner DSN 均是手动操作，不进入 web Pod。Helm render、镜像构建、真实集群、HTTPS、trusted-proxy 与 browser proof 仍归属 7.2d，保持 OPEN。Ingress 使用固定 redirect annotations，但真实 controller 必须保留默认 `nginx.ingress.kubernetes.io` annotation prefix，且 `no-tls-redirect-locations` 不得豁免 `/`；chart 本身不能配置这些 controller-level prerequisites。Helm lint/template 与 Docker image build 未验证；当前无 Helm render、真实集群或浏览器部署证据，不代表 M4b/M4 或 REQ acceptance。

**M4b implementation checklist（按顺序；当前未完成子步骤：M4b-7.2d、7.3b–7.6）：**

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
- [ ] **M4b-7.2d HTTPS ingress/trusted-proxy deployment validation（M5 硬门禁；M4 不阻塞）**：**2026-10-03 裁决**：正式生产/客户集群 ingress/trusted-proxy 证明与 **M5** 集群验收捆绑，**不是** M4 关门硬门禁。M4/M4b-8 浏览器同源 HTTPS 可用 **compose / 自签证书 / 本地反代** 收集证据（见 §4.2）。7.2d 仍须在未来完成：保留默认 `nginx.ingress.kubernetes.io` annotation prefix；确认 `no-tls-redirect-locations` 不豁免 `/`；客户 TLS Secret；真实客户端 redirect/拒绝与浏览器 credentials 不经 HTTP；显式 proxy IP/CIDR 的 forwarded scheme 信任。在 M5 记录真实 controller/deployment/browser evidence 前保持 OPEN。
- [x] **M4b-7.3a Live decisions on existing ChangeOrders（engineering slice only）**：live table/modal 支持 draft creator 提交既有 draft，以及由不同 approver 批准或拒绝 submitted order；API 禁止 creator 自拒绝。仅是现有 ChangeOrder 的 submit/approve/reject workflow，不提供规则 CRUD/create/edit/write，也不是 M4b/M4 或 REQ acceptance；route-mocked browser checks 与 focused API regression evidence 见 [`acceptance/report.md`](acceptance/report.md)。
- [ ] **M4b-7.3b ManagedRule write/approval integration**：**M4 范围** 被叫+前缀（裁决 [`reviews/m4-req-calling-regex-lossless-adjudication-2026-10-03.md`](reviews/m4-req-calling-regex-lossless-adjudication-2026-10-03.md)）。已交付：`runtime_bundle`、[ADR-0025](architecture/adr/0025-managed-rule-runtime-bundle.md)、managed-rules API、live console（M4 隐藏主叫/正则）、PG E2E `test_postgres_managed_rule_pipeline_integration.py`。**仍 OPEN**：PG E2E 维护者环境绿、M4b-8 被叫+前缀浏览器证据、7.3b 整项勾选（不等同 REQ/M4 验收）。
- [ ] **M4b-7.4 Live Call-ID trace integration（M4 关门延期）**：**2026-10-03 裁决**：REQ-F-13 / 7.4 **不纳入 M4 关门**；信令/集成栈就绪后 **补测**。实现前仍须定义 trace source/store 与 API contract；当前无可查询的 live Call-ID trace endpoint/store。
- [ ] **M4b-7.5 Real distribution/health/rollback integration（M4 范围；AS 全栈补测后置）**：**2026-10-03 裁决**；**engineering on `cur`**：PostgreSQL `as_instances`、notify（first batch）、health probe（testbed JSON）、**Operations fleet inventory console UI**、`test_fleet_api.py` 扩展。**未**声称 M4/REQ-F-15 验收；live distribution 浏览器链路与 **完整 AS 栈补测**仍为 follow-up（见 `acceptance/report.md` M4b-7.5）。
- [ ] **M4b-7.6 Full browser workflow integration**：**distribution UI slice（2026-10-03）** — change-order modal 内 start/report/rollback；**仍 OPEN** — 与规则 propose→审批→分发→apply 的 **整条浏览器链**、M4b-8 维护者签字证据；trace 仍缺；mock/preview 不满足。
- [ ] M4b-8 browser acceptance：验证 REQ-F-12/13/14/15 与 REQ-S-4 全部 flows（工程/AI 执行步骤并收集脱敏材料；**维护者审阅并签字**）。M4 可在 dev HTTPS（§4.2）上跑；7.2d 正式 preflight 属 M5。

主叫/正则匹配为 v1.1；M4 live 规则路径为被叫+前缀。M4b 与整体 M4 仍未验收。

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

M6 是一个带决策的研究里程碑，不是对某个数字的承诺。容量研究仍按原顺序留在 M6，并使用真实 socket；流量模型与负载生成器决策也留在 M6，不纳入 M4b。M7 在 M6 报告之前不启动。

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

**M4 工程证据维护者签字**：M4b 切片 reviews + M4b-8 artifacts/runbook **已记录 2026-10-04**（chat 授权代签）；**不**等于 REQ/M4 整体验收。**仍开放/后置**：7.4/F-13、F-15 AS **补测**、7.2d（M5）、REQ 级 acceptance。（规则匹配轴与 M4 被叫+前缀已裁决；ADR-0024 Accepted，2026-10-03。）

---

## 5. 未决项

### 5.1 从架构文档继承（§12.1）

| # | 条目 | 阻塞 | 解决所需 |
|---|---|---|---|
| O1 | 容量目标：CPS、并发会话、建立时延预算。**已有量级估计**（见 [`architecture/容量量级估算.md`](architecture/容量量级估算.md)：选型设计目标 ≥500 CPS / ≥20,000 并发对话），但**仍是未决项** —— 数字来自公开统计推算，非实测 | M7 集成容量验收、HPA 阈值（M5） | M6 的实测，在 harness 跑真实 socket 之后；须回收估算文档 §6 的 C1–C7；不再作为 SIP 栈选择依据 |
| O2 | **已选定 reSIProcate C++**（ADR-0019 Accepted）；生产栈方向不变。DUM/controller 集成与 E1/E4/E5 仍未验证 | D9、D10、M7 | ADR-0019 的选型结论不代替集成或需求验收；K2 未解除 |
| O3 | reSIProcate 生产路径的 SIP 行为验收（E1，S1–S11） | M7 / M8 | native DUM S1/S4 smoke 不是产品 E1；完成集成 spike 后由产品 adapter 通过真实 socket probe 验证 |
| O4 | 呼叫轨迹保留期 | M4 | 客户合规要求 |
| O5 | 容灾等级：N+1（节点）还是 N+M（机架 / AZ） | M5 Redis 拓扑 | 客户 SLA |

### 5.2 搭骨架时新增

| # | 条目 | 阻塞 | 说明 |
|---|---|---|---|
| D1 | **Python 3.10 在 2026 年 10 月到达生命周期终点。** 产品锁 3.10 是因为那是 sippy 验证过的版本。 | 该日期之后的任何交付 | 尽早验证 sippy 在 3.11 / 3.12 上的行为；要么迁移，要么在 ADR 里把 EOL 运行时登记为已接受的 risk。这里不定。 |
| D2 | ~~同一用例的第二个语言实现放置位置~~ **已不适用**：当前产品决策模块保持 Python；reSIProcate 集成边界由 D9 spike 处理 | — | 不启动第二个业务实现；跨实现一致性仍按语言无关契约验证（ADR-0012） |
| D3 | Redis 客户端与 Sentinel 接线；脑裂窗口下的判决幂等 | M2 | 风险 R5 |
| D4 | ~~控制台前端形态：保留 vendored 单包、无构建步骤，还是接受一套工具链~~ **已裁决（2026-10-01）**：使用纯 HTML/CSS/JavaScript，不引入 bundler、build tool 或前端 runtime 依赖 | —（已解决） | 当前 console 尚无 HTTP/runtime 前端；无构建步骤适合简单的 on-premises 交付。M4b-1 只交付可直接打开的静态预览，不代表 M4b 后端、鉴权、持久化、workflow integration 或验收已完成 |
| D5 | 呼叫轨迹存储：PostgreSQL，还是独立的短保留存储 | M4 | 与 O4 相关 |
| D6 | testbed 是否必须在 v1 支持客户验收测试 | M8 | 架构文档把它推迟到 v1.1 |
| D7 | ~~未决~~ **已裁决（2026-09-28）**：粒度固定为号段 + 稳定哈希百分比，schema 与判定幂等见 [ADR-0021](architecture/adr/0021-runtime-override-granularity.md) | M4 | 与 ADR-0020 的分层门控相关，需在控制面设计前定 |
| D8 | ADR-0014（三层 testbed）在 PRD 中找不到对应的需求编号：PRD 现行 REQ-NF-13 是"OTel 三信号导出"（已由 ADR-0005 承载），没有覆盖"testbed 三层"与"真实 socket 容量压测"。0014 暂以 REQ-NF-13 指向并在 Evidence 注明 | M8 / PRD 维护 | 需维护者裁决：补一条 testbed/容量压测的 REQ，或调整 0014 的指向 |
| D9 | reSIProcate DUM 到 Python 决策模块的产品集成方式及 adapter 边界未定；上游 `BUILD_PYTHON=ON` 不提供通用 DUM Python 模块。隔离 spike 已证明 CPython native callback、真实 DUM→Python→404/500 和一个两腿 486 分支可行，但未形成产品 API/adapter | M7 实现；K2 | 维护者评审桥接可行性证据并裁决产品 adapter 边界后，才授权实现；仍须补完整 E1、forking 与 final-response race 覆盖。业务决策继续使用 Python |
| D10 | 当前验收范围按 `docs/acceptance/test-plan.md`：基本呼叫完成 ACK 交换后 kill/restart AS，再由上游发送 in-dialog BYE；replacement 必须将 BYE 路由到对端且 Redis 中完整 dialog record 存在。跨进程 UAC `DialogSetId` + 应用保存字段的窄 re-INVITE hook 通过；fresh DUM 对该已建立 UAS dialog 的同 dialog BYE 返回 481，故当前 baseline 失败。产品两腿映射恢复仍未证明；未发现公开 UAS rehydrate API | M7 / M8；REQ-NF-1 验收 | **不通过 / 未解决，仍阻塞 M7/M8**：REQ-NF-1 保持硬要求，D10 必须通过当前 ACK-established-dialog BYE/Redis baseline。`SipStack` 在进程中途的 pending transaction recovery 尚未验证，但不属于当前 acceptance；若要加入 INVITE/CANCEL/final-response/2xx-ACK recovery，须单独修改/扩展 requirement 与 test plan 并经维护者裁决。用户已选择 Redis 应用层最小 checkpoint 方向并记录于仍为 proposed 的 ADR-0023；初版 `CallStateCheckpointRepository` 仅属 schema-v1 序列化/仓储 groundwork，尚未接入产品 DUM/CallController 恢复；不能将仓储或 UAC hook 当作完整恢复，也不得静默替换 ADR-0019 栈。详见[呼叫状态恢复方案比较](architecture/call-state-recovery-options.md)。 |
| D11 | 隔离 native DUM 路径已对有限 SDP 样本观察到 body 字节恒等：230/143/233 字节 offer，以及一个不同的 238 字节 answer；这不是完整产品 adapter 或 REQ-F-4 验收 | M7 / M8；REQ-F-4 验收 | 扩大到需求基线、stack 接受的边界变体及完整产品 adapter 路径，以 on-wire capture 比较 body 并完成 review；在此之前不得宣称 REQ-F-4 通过 |

**D10 的 M7 阻塞 TODO（依赖顺序；全部完成并有验收证据前保持“不通过 / 未解决”）**：

- [ ] **M7.1 产品恢复接入**：实现产品 reSIProcate DUM / `RecoveryTU` 恢复集成，验证 ACK-established UAS/UAC 双腿可由新进程重建。
- [ ] **M7.2 非阻塞恢复读取**：在 SIP callback 之外完成 Redis lookup，并以非阻塞 continuation 恢复处理；不得在 callback 中等待 Redis。
- [ ] **M7.3 CallController context restoration**：从完整、已提交的双腿 checkpoint 恢复产品 `CallController` context，并验证同 dialog 新到达 BYE 的路由。
- [ ] **M7.4 owner 与提交安全**：实现 owner generation/fencing、完整双腿 durable commit acknowledgement，以及依赖 checkpoint 的 SIP side effect 前 write-before-side-effect；旧 owner 不得继续产生 side effect。
- [ ] **M7.5 checkpoint 生命周期**：为活跃呼叫实现 TTL renewal 和 terminal cleanup，并覆盖续期、终态、重试及 owner 交接行为。
- [ ] **M7.6 D10 验收**：按当前 `docs/acceptance/test-plan.md` 完成 ACK 后 kill/restart、完整 Redis dialog record、replacement BYE 路由至 peer 的产品路径测试与 review。

本次 4 KiB extension payload、16 KiB checkpoint 与 30-day TTL 上限只是 payload / retention groundwork only，不实现上述恢复、提交或生命周期语义。此 TODO 序列仅覆盖当前 ACK-established-dialog baseline，不把 D10 扩展到崩溃时的 mid-transaction recovery；该可选未来范围须另行获得 requirement 与 test-plan 批准。

### 5.3 PM / AM / UM 产品管理能力缺口（需求待补）

以下是尚未完整需求化的产品能力缺口，不是 M4b 的隐含扩项；M4b 仅包含当前控制台的 REQ-S-4 基础鉴权与审计。

| 能力 | 已有部分能力 | 尚缺能力与下一步 |
|---|---|---|
| PM（Performance Management） | REQ-NF-13 提供 OTel metrics / traces / logs；M5 已有指标与告警规则工件 | 这些不是 PM 管理产品或工作流，也不代表已有 live dashboard。补充 PRD requirement 与验收标准后，可作为独立 feature 规划 |
| AM（Alarm Management） | REQ-NF-14 与 M5 告警规则集 | 尚无完整告警生命周期管理（ack / clear / suppress / history / operator workflows）。先补 PRD requirement 与验收标准，再单独规划 |
| UM（User Management） | M4b-6a 在 ADR-0024（accepted）下提供基础本地账号、角色、密码与 session engineering slice；M4b-6b 后续交付 durable audit API/store engineering slice。两者均不构成 REQ-S-4 acceptance，也不代表 M4b 完成 | UM 仍是独立缺口：尚无获批的完整 UM requirement / acceptance，覆盖完整 operator account lifecycle、UI/workflows、SSO / MFA、password recovery / lockout / session UX。继续在 base scope 之外单独规划；不并入或据此标记完成 M4b |

在上述需求与验收标准获批前，不把 PM / AM / UM 的未定义功能并入 M4b。

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
