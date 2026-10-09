# 3GPP / GSMA / RFC 规范符合性矩阵

> **状态块（阅读本文前先看这里）**
>
> - **产品名**：**In-house IMS Application Server（文档暂用名）**，首现处标注 3GPP Third-Party AS role，下文简称 in-house AS。该名称**不是已正式批准的产品名**（`docs/plan.md` §0「产品决策记录」；[`../product-packaging-plan.md`](../product-packaging-plan.md) §4.3）。git repo 名拟改为 `inhouse-ims-as`（仅仓库名 / remote URL）；chart name、镜像名、OTel 服务名**保持 `3rdparty-as` 不变**。
> - **本文件归属**：[`../product-packaging-plan.md`](../product-packaging-plan.md) §1 第一批交付物 **1.2（3GPP 规范符合性矩阵）**。本文**尚无 review record**，按 `AGENT.md` §3.3 待维护者评审。
> - **四态定义**：**Fully**（已实现且有仓库内证据）／**Partial**（部分实现或有已知缺口）／**N/A**（按范围决策不适用，必须写理由）／**open**（证据不足，禁止断言符合）。计划文档中的「N-A」即本文的 **N/A**。
> - **证据规则**：每个 Fully / Partial 单元格必须给出 `file:line` 或契约场景号（S1–S12）；**找不到证据一律不写 Fully**，只写 open。
> - **生产栈**：**reSIProcate**（C++，Vovida 许可），ADR-0019 **accepted**。**sippy 仅是 testbed 行为基线**（`testbed/contracts/sip-baseline/README.md:1-6`），**不进入生产依赖**；`platform/` 生产路径不使用 sippy。
> - **未验收声明**：**E1（S1–S11 产品路径真实 socket 对拍）、E4（S12 TLS 证书热轮换）、E5（状态外置与进程重启恢复）均未验收**，待 M8 验收（ADR-0019 §6 步骤 5「接受的缺口」、§10；[`../plan.md`](../plan.md) §5.1 O2/O3）。native DUM 自环 smoke **不是** 产品 E1、不是需求验收（ADR-0022 Evidence）。
> - **testbed 证据边界**：ADR-0014 明确 v1 不把 testbed 作为交付物（[`../product-packaging-plan.md`](../product-packaging-plan.md) §0.3 第 8 条）；仿真结果（含 M7.1 仿真平台、callload、M6 dev-host harness）是研发/演示资产，**不得充当运营商 IOT 或现网证据**，引用时一律标注「内部测量 / 非对外」。
> - **本文不含容量数字**：O1（容量目标）**未裁决**（[`../plan.md`](../plan.md) §5.1），`AGENT.md` §2 禁止在实测裁决前发布任何 CPS / CAPS / BHCA / 并发 / 时延数字。文中出现的 `5060` / `5061` 是**协议端口常量**，不是容量指标（[`deploy/helm/values.yaml`](../../deploy/helm/values.yaml) L148 原文即如此注明）。
> - **术语纪律**：**RC 就绪 ≠ 通过**。M8 发布候选产物就绪，**退出签字仍搁置**（[`../acceptance/report.md`](../acceptance/report.md) §0 状态行）。

---

## 1. 范围与判定方法

### 1.1 适用范围

- **覆盖对象**：In-house IMS AS 的**对外 SIP 接入面**（S-CSCF → S-SBC → AS 的 ISC 触发信令）与**内部判决面**；控制面内部 API 不在本矩阵逐条展开。
- **网络角色**：运营商 IMS 网络**之外**的第三方 Application Server；S-CSCF / S-SBC / HSS 是运营商网元，仅作 `testbed/` 仿真器（`AGENT.md` §1）。
- **接入语义**：**仅 ISC 一种**（ADR-0003 accepted）。iFC 触发逻辑在 S-CSCF/HSS 侧，AS 侧不做 iFC 灰度（评审 G-P0-5）。
- **不覆盖**：媒体面、计费面、Diameter 面、合规章节（PDPO 见交付物 3.4）、容量章节（受 O1 阻塞）。

### 1.2 四态判定

| 状态 | 判定条件 | 允许的表述 |
|---|---|---|
| **Fully** | 行为已实现，**且**有 `file:line` 或契约场景号可查，**且**不依赖未验收的 E1/E4/E5 | 「已实现」 |
| **Partial** | 已实现但存在已知缺口、只覆盖部分码/部分场景，或实现只在工程切片 / testbed harness 上验证 | 「部分实现，缺口：…」 |
| **N/A** | 按已记录的范围决策**不适用**；必须写一行理由与依据 | 「不适用，理由：…」 |
| **open** | 无仓库内证据，或证据仅为文档描述、纸面评估、待人工核对规范原文 | 「待核对，阻塞：…」 |

> **当前本文没有任何单元格标为 Fully**：所有正向能力都至少依赖 E1 / E4 / E5 之一，而这三项**尚未验收**（ADR-0019 §6 步骤 5、§10）。这是如实状态，不是遗漏。

### 1.3 证据等级

- **A** —— 产品代码 + 对应单测 / 集成测试（`file:line` 可查）：可支撑 Fully / Partial。
- **B** —— 仅产品代码（无对应测试）：上限 Partial。**C** —— 仅文档 / ADR / 纸面评估：上限 open。
- **D** —— 无证据（仓库内未留存规范原文或无逐条实现）：只能 open。

**本文引用的具体证据文件**（供评审抽查）：`platform/src/as_platform/sip/{adapter,call_controller,message,transport,ingress,resip_runtime}.py`、`platform/native/resip_runtime/runtime_module.cxx`、`platform/tests/{test_call_controller,test_call_controller_recovery,test_sip_message,test_transport_seam,test_transport_ingress,test_resip_runtime_integration,test_resip_runtime_tls_policy_integration,test_resip_two_leg_integration,test_m7_forward_two_leg_integration,test_req_f4_sdp_identity_integration,test_d10_req_nf1_redis_integration}.py`、`apps/translation/src/as_translation/{decision,outbound}.py`、`apps/anti-fraud/src/as_anti_fraud/decision.py`、`testbed/contracts/{sip-baseline,decision}/`、`testbed/simulators/src/as_simulators/{bridge,sut}.py`、`deploy/helm/values.yaml`。

> **Release 适用性纪律**：TS 24.229 等 3GPP 规范的具体 Release **未逐条核对**，本文凡涉及 release 的判断一律记 `open（未逐条核对）`，**不写「符合 Release X」**。

---

## 2. 汇总表

| 规范 / 文档 | 适用性 | 状态 | 一句话结论 | 详见 |
|---|---|---|---|---|
| 3GPP TS 24.229（IMS SIP，ISC 触发） | 适用 | **Partial** | ISC 触发后的入腿判决、双腿 B2BUA、非 2xx 分支已实现并有证据；条款级符合性未逐条核对，记 open | §3.1 |
| 3GPP TS 29.228 / 29.229（Cx） | **不适用** | **N/A** | Cx 是 HSS 与 S-CSCF 之间的接口，属运营商网元内部接口，AS 不涉及 | §3.2 |
| 3GPP TS 29.328 / 29.329（Sh） | **不适用** | **N/A** | AS 数据来自自有数据面，不与 HSS 交互 | §3.3 |
| 3GPP TS 32.260 / 32.299（计费 / CDR） | **不适用** | **N/A** | 不采集、不投递、不批价、不归档话单 | §3.4 |
| GSMA IR.92 | 适用（IMS profile / 互通性） | **open** | 仓库内**未留存规范原文**，也无逐条实现证据；待人工核对原文后逐条确认 | §3.5 |
| GSMA IR.94 | 适用（媒体与安全基线） | **open** | 同上；本文只描述该文档通常涵盖的范围，不作条款断言 | §3.5 |
| RFC 3261（SIP） | 适用 | **Partial** | 消息构建、状态码、头处理、Dialog/B2BUA、CANCEL/487 有实现；forking / 3xx / REFER / PRACK-UPDATE 交错未实现 | §3.6 |
| RFC 6733（Digest 认证） | **不适用** | **N/A** | 不实现 digest；对端准入靠白名单 + mTLS | §3.7 |
| RFC 8688（ToS-SIP / `608 Rejected`） | 适用（能力声明可出现） | **open** | 拒绝口径是 `603 Decline`；`608` **未实现**，与部分文档描述不一致 | §3.8 |
| RFC 4566（SDP） | 适用（仅透传） | **Partial** | body 逐字节透传，AS 不解析、不改写、不锚定媒体 | §3.6.9 |
| RFC 3265 / 3325 / 3326 / 3428 | 适用性待评估 | **N/A** | 产品代码无命中（`MIN-SE` / RTP/RTCP / RAck / `Reason:`），不做媒体即不适用；逐条理由见 §3.6.9 | §3.6.9 |

---

## 3. 逐规范矩阵

### 3.1 3GPP TS 24.229 —— IMS SIP，ISC 触发

> **条款级符合性：open（未逐条核对）**。仓库内**未留存 TS 24.229 原文**（`docs/README.md` L34 规划了 `docs/specs/` 目录，但该目录**不存在**），因此下表**不引用任何条款号**，只登记「能力项 → 仓库内证据」。规范原文需人工取回后逐条核对。

| 能力项（条款号未逐条核对） | 适用性 | 状态 | 实现位置（file:line） | 证据 | 备注与阻塞 |
|---|---|---|---|---|---|
| S-CSCF 触发后向 AS 发起初始 INVITE（ISC） | 适用 | **Partial** | `platform/src/as_platform/sip/resip_runtime.py:330`、`platform/native/resip_runtime/runtime_module.cxx:979` | A：`testbed/simulators/tests/test_product_path.py`（integration，跨仿真 S-SBC 且**不用** accept-all） | 只验收到入腿并判决；两侧全链路对拍属 E1，未验收 |
| 入腿按业务规则判决（FORWARD / TRANSLATE / DECLINE / NOT_FOUND） | 适用 | **Partial** | `platform/src/as_platform/sip/adapter.py:128-148`、`platform/src/as_platform/sip/call_controller.py:82-95` | A：`platform/tests/test_call_controller.py`、`apps/*/tests/test_contract_replay.py` | 判决是纯函数；规则集来自配置，非 SIP 语义 |
| 无匹配规则 → `404 Not Found` | 适用 | **Partial** | `platform/src/as_platform/sip/adapter.py:25` | A：契约场景 `S2-no-match-404`（`testbed/contracts/sip-baseline/README.md:13`） | 产品路径已实现；基线由 sippy 抓取，对拍属 E1 |
| 策略拒绝 → `603 Decline` | 适用 | **Partial** | `platform/src/as_platform/sip/adapter.py:24`；反诈超限 `apps/anti-fraud/src/as_anti_fraud/decision.py:152-156` | A：契约场景 `S3-policy-reject-603`（同 README L14） | 与 RFC 8688 `608` 的口径差见 §3.8 |
| 双腿 B2BUA（两腿独立 Call-ID） | 适用 | **Partial** | `platform/native/resip_runtime/runtime_module.cxx:1057-1103` | A：`platform/tests/test_resip_two_leg_integration.py`、`test_m7_forward_two_leg_integration.py` | 14 条消息全文回放未签收（`../acceptance/test-plan.md` L30） |
| S-SBC 透明桥接 | **不适用**（运营商侧） | **N/A** | — | 仿真器 `testbed/simulators/src/as_simulators/bridge.py:1-6` | 理由：S-SBC 是运营商网元，不是我方交付物（ADR-0003） |
| Release 适用性 | — | **open** | — | D：仓库内无原文 | 待人工核对规范原文后填写 |

### 3.2 3GPP TS 29.228 / 29.229 —— Cx

| 能力项 | 适用性 | 状态 | 依据 |
|---|---|---|---|
| Cx（Diameter S-CSCF ↔ HSS） | **不适用** | **N/A** | **理由**：Cx 是 HSS 与 S-CSCF 之间的接口，属**运营商网元内部接口**；AS 位于 IMS 网络之外、由 S-CSCF 经 S-SBC 以 ISC 触发，不与 HSS 建立 Diameter 会话（`AGENT.md` §1「只实现外部 AS」；[`../architecture/新系统整体架构.md`](../architecture/新系统整体架构.md) §9.2 把「Diameter Sh 接口」列入明确排除）。仓库内**无任何 Diameter/Cx 代码或配置命中**。 |

### 3.3 3GPP TS 29.328 / 29.329 —— Sh

| 能力项 | 适用性 | 状态 | 依据 |
|---|---|---|---|
| Sh（Hx / Diameter Sh / SWx 相关订阅数据） | **不适用** | **N/A** | **理由**：AS 的业务数据来自**自有数据面**（规则集、号码翻译表、反诈限额），不需要向 HSS 查询订阅数据，因此不做 Diameter Sh（`AGENT.md` §2 非目标「不做 Diameter Sh。数据来自我们自己的数据面」；[`../architecture/新系统整体架构.md`](../architecture/新系统整体架构.md) §9.2 L480）。评审 G-P0-4 已裁决：Grafana 面板与告警**均不含 Sh**，合规矩阵中 Sh 标 N/A（[`../reviews/product-packaging-plan-review-2026-10-09.md`](../reviews/product-packaging-plan-review-2026-10-09.md) L352）。 |

### 3.4 3GPP TS 32.260 / 32.299 —— 计费 / CDR

| 能力项 | 适用性 | 状态 | 依据 |
|---|---|---|---|
| 呼叫记录（CDR）生成、投递、归档 | **不适用** | **N/A** | **理由**：不采集、不投递、不归档、不批价（`AGENT.md` §2；ADR-0017 accepted）。以按 **Call-ID** 的呼叫轨迹替代话单，用于投诉追溯与反诈举证（[`one-pager.md`](one-pager.md) §2「呼叫记录」行）。 |
| 计费网元交互、话单分发 | **不适用** | **N/A** | **理由**：计费数据归属运营商计费域，网外第三方 AS 不介入（同上；[`../architecture/新系统整体架构.md`](../architecture/新系统整体架构.md) §9.2 L478）。 |

### 3.5 GSMA IR.92 / IR.94

> **整节状态：open（待人工核对规范原文后逐条确认）**。仓库内**未留存 IR.92 / IR.94 原文**（无 `docs/specs/` 目录，见 §3.1 说明），也无逐条实现证据。下表**只描述该文档通常涵盖的范围**，**不含任何条款号断言、不含「已符合」结论**。取回原文后按 §1.3 证据等级逐条改写。

| 范围（通常涵盖，非条款断言） | 适用性 | 状态 | 可间接参考的仓库事实 | 阻塞 |
|---|---|---|---|---|
| IR.92：IMS profile / 互通性（IMS 终端与网络侧互通行为、参数取值） | 适用 | **open** | 无直接实现证据；`platform/src/as_platform/sip/message.py:38-48` 只落实 RFC 3261 的必备头与 magic cookie | 待人工核对规范原文 |
| IR.94：媒体与安全基线（含承载与安全要求） | 部分适用 | **open** | 本产品**不做媒体**（`AGENT.md` §2、ADR-0004），因此 IR.94 的媒体侧条款大部分不适用；安全侧仅有白名单 + 端到端 TLS（ADR-0016） | 待人工核对规范原文 + 需先裁决哪些条款随「不做媒体」而 N/A |

### 3.6 RFC 3261 —— SIP

#### 3.6.1 方法

| 能力项 | 适用性 | 状态 | 实现位置（file:line） | 证据 | 备注 |
|---|---|---|---|---|---|
| 初始 INVITE（UAS 入腿） | 适用 | **Partial** | `platform/native/resip_runtime/runtime_module.cxx:979-1055` | A：`platform/tests/test_resip_runtime_log_contract.py` 等 | 14 条全文未签收 |
| ACK | 适用 | **Partial** | 由 DUM 处理；`accept_all_invites` harness 下固定 100/180/200/ACK（`platform/src/as_platform/sip/README.md:7-8`） | C：harness 性质 | `accept_all_invites` 是 testbed-only，**不是生产路径** |
| BYE | 适用 | **Partial** | 入腿 BYE → 出腿 `end()`：`runtime_module.cxx:1117-1140` | A：`platform/tests/test_d10_req_nf1_redis_integration.py`（恢复后 in-dialog BYE） | 恢复路径有工程实现，**产品路径未验收** |
| CANCEL（主叫放弃，含 487 分支） | 适用 | **Partial** | `runtime_module.cxx:1226-1242`（`early_cancel_harness` 保持早期态）；B2BUA CANCEL 见 `README.md:19` | A（仅 harness 形态）+ C | 竞态（S11）基线缺失，见 §4 |
| REFER / 呼叫转移 | 适用 | **open（未实现）** | `runtime_module.cxx:1251-1260`：`onRefer` / `onReferNoSub` / `onReferRejected` / `onReferAccepted` **均为空实现** | A（空实现即证据） | ADR-0019 §5.1 把 REFER 列为非门槛待补场景 |
| forking | 适用 | **open（未实现）** | `runtime_module.cxx:1182`：`onForkDestroyed` 空 | A（空实现即证据） | ADR-0019 §5.1 |
| 3xx 重定向 | 适用 | **open（未实现）** | `runtime_module.cxx:1183`：`onRedirected` 空 | A（空实现即证据） | ADR-0019 §5.1 |
| PRACK / UPDATE 交错 | 适用 | **open（未实现）** | 产品代码无对应处理分支 | D：无命中 | ADR-0019 §5.1 |
| re-INVITE（hold / resume） | 适用 | **open（未实现）** | `platform/src/` 无 hold/resume 业务分支；仅 D10 probe 恢复过 in-dialog re-INVITE（ADR-0022 Evidence） | C（probe，非产品代码） | ADR-0019 §5.1 |

#### 3.6.2 状态码

| 能力项 | 适用性 | 状态 | 实现位置（file:line） | 证据 | 备注 |
|---|---|---|---|---|---|
| `404 Not Found` | 适用 | **Partial** | `adapter.py:25,145-146` | A：契约场景 S2 | — |
| `603 Decline` | 适用 | **Partial** | `adapter.py:24,142-143` | A：契约场景 S3 | 见 §3.8 的 603/608 口径 |
| `403 Forbidden`（入腿未授权） | 适用 | **Partial** | `platform/src/as_platform/sip/resip_runtime.py:39,334-346` | A：`platform/tests/test_resip_runtime_integration.py:151`、`test_resip_runtime_tls_policy_integration.py:175-196`、`test_resip_runtime_tls_integration.py:222` | 明文被拒与白名单未命中**共用** 403 |
| `500`（异常 / 无路由） | 适用 | **Partial** | `runtime_module.cxx:1044,1051` | A | 回调抛异常与 `statusCode == 0` 两条路径 |
| 下游非 2xx **逐码透传集合 {408, 480, 486, 503, 504}** | 适用 | **Partial** | `platform/src/as_platform/sip/call_controller.py:19-21,98-104`；native 同逻辑 `runtime_module.cxx:466-484` | A（Python 侧）+ A（native 侧映射函数） | **native 产品路径只对 `486` 有端到端测试**（`test_resip_two_leg_integration.py`、`test_m7_forward_two_leg_integration.py`）；其余四码无产品路径证据 |
| 其余 4xx–6xx 统一映射 `502 Bad Gateway` | 适用 | **Partial** | `call_controller.py:20,100-104`；`runtime_module.cxx:479-483` | B | **Partial 理由**：映射规则已实现并有单测，但产品路径未对非透传集合的码做端到端验证。另注：独立两腿 spike 的口径更窄（`platform/native/resip_two_leg/two_leg_module.cxx:358` 只映射 `486`，其余一律 502），**spike 不是生产适配器** |
| `487 Request Terminated` | 适用 | **Partial** | `runtime_module.cxx:1226-1242`（harness 保持早期态使 DUM 回 487） | A（harness）+ C | 产品路径的两分支完整语义待 E1 |
| 其它 1xx/2xx/3xx 码 | 适用 | **open** | — | D | 未逐条核对 |

#### 3.6.3 头字段

| 能力项 | 适用性 | 状态 | 实现位置（file:line） | 证据 | 备注 |
|---|---|---|---|---|---|
| 请求必备头（To / From / CSeq / Call-ID / Max-Forwards / Via） | 适用 | **Partial** | `platform/src/as_platform/sip/message.py:44-45,369-378` | A：`platform/tests/test_sip_message.py` | 缺失即 `ValueError`，不会发出残缺请求 |
| `Via` branch magic cookie `z9hG4bK` | 适用 | **Partial** | `message.py:47-48,381-388` | A | 模块**不生成** branch（禁止读时钟 / 取随机，ADR-0002） |
| `Content-Length` 按 body 字节数覆写 | 适用 | **Partial** | `message.py:41-42,314-327` | A | 覆写为原地覆盖，保持调用方字段顺序 |
| body 逐字节透传（SDP 不重编码） | 适用 | **Partial** | `message.py:12-16,72-73,442-458`；native 转发 `runtime_module.cxx:1204-1205` | A：`platform/tests/test_req_f4_sdp_identity_integration.py` | REQ-F-4 **签收未完成**（[`../plan.md`](../plan.md) §5.2 D11） |
| 重复头保持重复（不折叠） | 适用 | **Partial** | `message.py:61-78,214-254` | A | 以 `(name, value)` 序列承载 |
| Route 消费 / Record-Route route set 抽取 | 适用 | **Partial** | `runtime_module.cxx:840-856`（`buildRouteSetList`）、`:606,645,699` | A（抽取）+ D（翻腿行为端到端） | 基线 S8 由 S1 同 capture 覆盖；S9 缺失（§4） |
| 出腿 `Request-URI`：只改 user，host/port 取自 `AS_SIP_NEXT_HOP` | 适用 | **Partial** | `apps/translation/src/as_translation/outbound.py:43-52,63-88` | A：`apps/translation/tests/` | TLS 用 `sips:`；user 改写只在 TRANSLATE 判决时发生 |
| `Contact` 在 TLS 场景改写为 TLS 端口 | 适用 | **Partial** | `runtime_module.cxx:51-91`（`TransportContactDecorator`），装机点 `:1456` | B（代码）+ C（testbed A/B reload 记录） | 仅对**响应**的首个 Contact 改 `scheme=sips` + `port`，并移除 `transport` 参数 |
| AS 自身是否插入 Record-Route | 适用 | **open** | 产品代码未显式设置（`runtime_module.cxx` 无 Record-Route 插入点） | D | 行为由 DUM 默认决定；需人工核对规范原文后确认是否符合预期 |
| `Diversion` / `History-Info` / `Replaces` / `Privacy` | 适用 | **N/A** | 代码无命中 | D（grep 无匹配） | **理由**：本产品只做号码翻译与反诈判决，不做呼叫Diversion / 历史信息 / 呼叫转移替换 / 隐私标识处理。仅在 POC 抓包基线文本中作为运营商侧字段出现，产品代码不解析也不改写 |
| `P-Asserted-Identity` | 适用 | **open** | 产品 runtime 不解析；仿真 SUT 读取以取主叫（`testbed/simulators/src/as_simulators/sut.py:183-184`）；checkpoint 头扩展机制以它作测试样例（`platform/tests/test_call_state_checkpoint.py:82`） | B/C | **不是 N/A**：ADR-0019 §5.1 把「`P-Asserted-Identity` 与信任域白名单校验」列为**待补场景**；产品路径的白名单校验对象是**证书指纹 / IP**，不是 PAI |

#### 3.6.4 Dialog 与 B2BUA

| 能力项 | 适用性 | 状态 | 实现位置（file:line） | 证据 | 备注 |
|---|---|---|---|---|---|
| B2BUA：UAS 腿与 UAC 腿独立、各自 Call-ID | 适用 | **Partial** | `runtime_module.cxx:1057-1103`；`call_controller.py:31-49` | A：`platform/tests/test_resip_two_leg_integration.py` | 恢复后腿标识从 checkpoint 重建：`call_controller.py:236-255` |
| 腿关联与在途状态清理 | 适用 | **Partial** | `call_controller.py:115-120,170-230` | A：`platform/tests/test_call_controller.py` | 控制器为**内存态**，可恢复上下文单列 checkpoint |
| 每腿独立 Via / 事务定时器归属 | 适用 | **Partial** | 由 DUM / `SipStack` 拥有（ADR-0022 Decision） | C | 控制器不重复实现重传与定时器 |

#### 3.6.5 CANCEL 与 487

| 能力项 | 适用性 | 状态 | 实现位置（file:line） | 证据 | 备注 |
|---|---|---|---|---|---|
| 入腿 CANCEL → `200 OK`，并向下游发 CANCEL | 适用 | **Partial** | `platform/src/as_platform/sip/README.md:18-19`；`runtime_module.cxx:1226-1242` | A（harness 形态） | 产品路径语义依赖 DUM 行为，尚无产品路径端到端签收 |
| 主叫放弃 → `487` | 适用 | **Partial** | 同上 | A（harness）+ C | ADR-0022 记录 DUM 对入腿初始 INVITE CANCEL 回 200/487 并报 `RemoteCancel` |
| CANCEL 与最终响应竞态（S11） | 适用 | **open** | — | D | POC 无竞态测试，基线缺失（§4） |

#### 3.6.6 in-dialog 请求

| 能力项 | 适用性 | 状态 | 实现位置（file:line） | 证据 | 备注 |
|---|---|---|---|---|---|
| 恢复后 in-dialog BYE 按 Route 回送下游 | 适用 | **Partial** | `call_controller.py:257-262`；`runtime_module.cxx:1117-1140` | A：`platform/tests/test_call_controller_recovery.py`、`test_d10_req_nf1_redis_integration.py` | **工程切片，非 REQ-NF-1 签收**（[`../plan.md`](../plan.md) §5.2 D10） |
| 其它 in-dialog 请求（re-INVITE / UPDATE / INFO / MESSAGE / NOTIFY） | 适用 | **open** | `runtime_module.cxx:1244-1250` 回调为空 | A（空实现即证据） | 与 §3.6.1 方法表一致 |

#### 3.6.7 传输与 TLS

| 能力项 | 适用性 | 状态 | 实现位置（file:line） | 证据 | 备注 |
|---|---|---|---|---|---|
| SIP over UDP `5060` | 适用 | **Partial** | `deploy/helm/values.yaml:150-153`；`platform/src/as_platform/runtime/sip_stack_service.py:168-169` | A（helm chart-check / values） | 端口是协议常量，非容量数字 |
| SIP over TLS `5061` | 适用 | **Partial** | `deploy/helm/values.yaml:153`；`sip_stack_service.py:171` | A | 同上 |
| SIP over TCP | 适用 | **Partial** | `sip_stack_service.py:157-159,170`（`AS_SIP_ENABLE_TCP` 开启，端口取 `AS_SIP_TCP_PORT` / `SIP_LISTEN_PORT`，默认 `0` = 不监听） | A | **TCP 默认关闭**。另注：`deploy/docker/Dockerfile:37` 把 `5061/tcp` 暴露为容器端口，与 values.yaml 中 5061 = TLS 的口径**不一致**，属文档/打包口径 open 项 |
| 要求 TLS 时明文在解析前被拒 | 适用 | **Partial** | `platform/src/as_platform/sip/ingress.py:24,178-194`；调用点 `resip_runtime.py:296-298,334-335` | A | 明文拒绝**先于** `decide()` 与消息解析 |
| 证书热轮换（不重启、不丢在途呼叫） | 适用 | **open** | 机制：`ingress.py:70-100`（重叠窗口）、`runtime_module.cxx:1497-1501`（`SipStack::reloadCertificates()`）、`runtime_module.cxx:1706-1720`（Python 入口） | C（testbed-only smoke） | **E4 无实验室证据 → open**（ADR-0019 §6 步骤 5 第 2 条、§10；native TLS S1 曾以 503 Certificate Validation Failure 失败）。**不得**表述为已通过验收 |

#### 3.6.8 安全

| 能力项 | 适用性 | 状态 | 实现位置（file:line） | 证据 | 备注 |
|---|---|---|---|---|---|
| 对端白名单（IP / CIDR / `host:port` / 证书指纹） | 适用 | **Partial** | `platform/src/as_platform/sip/transport.py:48-63,249-298` | A：`platform/tests/test_transport_seam.py` | 证书命中或地址命中**任一**即放行（ADR-0016） |
| 空策略 fail-closed | 适用 | **Partial** | `transport.py:257-273` | A | Helm 侧另有渲染期 fail-closed 开关 `allowEmptyAllowlistForTest`（`values.yaml:162-165`），默认 `false` |
| 默认要求客户端证书（mTLS） | 适用 | **Partial** | `transport.py:75-93`（`require_client_certificate: bool = True`，且 `ca_path` 为空即报错） | A | 例外：harness / 仿真链路可关闭 |
| SRTP / 媒体加密 | **不适用** | **N/A** | — | — | **理由**：不做媒体，无 SRTP（`AGENT.md` §2、ADR-0004：媒体需求由网内 MRF 承担，AS 只给判决） |

#### 3.6.9 其它 RFC（SDP / MIN-SE / RTP-RTCP / RAck / Reason）

| 能力项 | 适用性 | 状态 | 依据 |
|---|---|---|---|
| RFC 4566（SDP） | 适用（仅透传） | **Partial** | `platform/src/as_platform/sip/message.py:12-16`（body 逐字节透传，AS 不解析 SDP）；`NOTICE:34` 登记为 pass-through only。证据 A：`platform/tests/test_req_f4_sdp_identity_integration.py`。**REQ-F-4 签收未完成** |
| RFC 3265（`MIN-SE`） | 适用性待评估 | **N/A** | **理由**：产品代码无 `MIN-SE` 命中；会话定时器能力归 DUM 所有（ADR-0022 Decision），不由 AS 应用层实现 |
| RFC 3325（RTP/RTCP） | **不适用** | **N/A** | **理由**：不做媒体（ADR-0004）；代码无 RTP/RTCP 命中 |
| RFC 3326（RAck） | 适用性待评估 | **N/A** | **理由**：可靠临时响应由 SIP 栈（`SipStack`）的事务层拥有，AS 应用层不实现（ADR-0022 Decision：控制器不得重复栈事务与重传）；代码无 `RAck` 命中 |
| RFC 3428（`Reason:` 头） | 适用性待评估 | **N/A** | **理由**：产品代码无 `Reason:` 构造命中，失败以状态码本身表达（`call_controller.py:98-104`） |

> 本表各行一律以「代码无命中 → N/A」为依据，**不做规范条款推断**。

### 3.7 RFC 6733 —— SIP Digest 认证

| 能力项 | 适用性 | 状态 | 依据 |
|---|---|---|---|
| HTTP Digest 认证（`WWW-Authenticate` / `Authorization` / nonce） | **不适用** | **N/A** | **理由**：AS 作为 IMS 信任域内的信令端点，**不实现 digest 认证**；对端准入靠 **TLS 端到端 + 对端白名单（IP/CIDR/证书指纹）** 组合判定（ADR-0016；`platform/src/as_platform/sip/transport.py:249-298`）。仓库内**无任何 digest / `WWW-Authenticate` / nonce 处理命中**（`platform/` 内 `digest` 仅出现在 FNV 哈希 `platform/src/as_platform/gating/overrides.py:73` 与证书指纹计算 `runtime_module.cxx:224-232`，均与 SIP digest 认证无关）。 |

### 3.8 RFC 8688 —— ToS-SIP / `608 Rejected`

| 能力项 | 适用性 | 状态 | 实现位置 | 证据 | 备注 |
|---|---|---|---|---|---|
| 能力声明 `+sip.608` | 适用（被动出现） | **Partial** | 出现在 POC 抓包基线的入腿 INVITE（`testbed/contracts/sip-baseline/S1-basic-call/01-in-invite-trunk.txt:19` 等） | A（基线文本） | 这是**运营商侧对端**的声明，AS 自身不发此 Feature-caps |
| 以 `608 Rejected` 应答反诈/屏蔽判决 | 适用 | **open（未实现）** | 产品路径**发 `603 Decline`**（`adapter.py:24,142-143`；反诈超限 `apps/anti-fraud/src/as_anti_fraud/decision.py:152-156`） | A | 判决模块注释明确把 608 归为「适配层的关注点，**不是本模块的**」（`decision.py:22-25`） |
| 文档一致性 | — | **open** | — | D | **口径差注记**：`608 Rejected (RFC 8688)` 仍出现在 `apps/README.md:8`、`apps/anti-fraud/README.md:3`、`apps/anti-fraud/pyproject.toml:4` 的描述、以及 [`../architecture/新系统整体架构.md`](../architecture/新系统整体架构.md) L80 的 POC 现状描述中，与产品代码实际发的 `603` **不一致**。**本矩阵以代码为准**：产品路径当前只发 `603`。是否新增 608 需新 ADR + 契约变更 |

---

## 4. 测试证据基线

### 4.1 契约场景 S1–S12 覆盖度

依据 [`../../testbed/contracts/sip-baseline/README.md`](../../testbed/contracts/sip-baseline/README.md)（L10-31）。基线由 **sippy** 在 POC 上抓取，只记录**外部可观测消息行为**，不记录 sippy API。

| 场景 | 内容 | 基线状态 | 产品路径证据 | 判定 |
|---|---|---|---|---|
| S1 | 基本呼叫 INVITE→100→180→200→ACK→BYE→200 | ✅ 已抓取 | `accept_all_invites` harness 覆盖入向 100/180/200（带 SDP） | Partial（14 条全文未签收） |
| S2 | 无匹配规则 → `404` | ✅ 已抓取 | 走 `decide()` | Partial |
| S3 | 策略拒绝 → `603` | ✅ 已抓取 | 走 `decide()` | Partial |
| S4 | 主叫放弃 → CANCEL → `200 OK` → `487` | ✅ 已抓取 | `early_cancel_harness` 保持早期态 | Partial（harness 形态） |
| S5 | 双腿 B2BUA，两侧 Call-ID 不同 | ✅ S1 同 capture | `test_resip_two_leg_integration.py` | Partial |
| S6 | Request-URI 改写 | ✅ S1 同 capture | `apps/translation/src/as_translation/outbound.py:63-88` | Partial |
| S7a | SDP 完全透传 | ✅ S1 同 capture | `test_req_f4_sdp_identity_integration.py` | Partial（签收未完成） |
| S7b | SDP 按契约改写 | ❌ 基线缺失（POC 无此功能） | — | open |
| S8 | Route / Record-Route 处理 | ✅ S1 同 capture | `runtime_module.cxx:840-856` 抽取 route set | Partial |
| S9 | in-dialog 请求路由 | ⚠️ POC 有 chained probe，`capture_call.py` 不跑，需间接推断 | 恢复后 in-dialog BYE 有工程测试 | open（基线为间接推断） |
| S10 | 非 2xx（`486` / `480` / `408`）分支 | ❌ 基线缺失（POC ReturnUas 只回 200） | 产品路径仅 `486` 有端到端测试 | Partial（仅 486） |
| S11 | CANCEL 与最终响应竞态 | ❌ 基线缺失 | 无 | open |
| S12 | TLS 证书热轮换（E4 硬约束，非 E1 门槛） | ❌ 未完成（ADR-0019 §6 步骤 5 第 2 条） | 仅 testbed-only smoke | **open（E4）** |

### 4.2 判决契约

[`../../testbed/contracts/decision/`](../../testbed/contracts/decision/) 是**判决契约**（数据，不是抓包）：`cases.json` 共 **14 个 case**，字段语义见其 `README.md:29-79`。

- 判决 outcome 四值：`forward` / `translate` / `decline` / `not_found`；规则 action 三值：`forward` / `translate` / `block`，其中 `block` → `decline`（`README.md:46-49`）。
- `applies_to` 三值：`both` / `translation` / `anti-fraud`。同一输入在 TRANSLATE 时两侧**故意不同**：内核把出腿号码留空，由 translation 用例填回，anti-fraud **刻意不改写**（`README.md:63-78`）。
- 重放：`uv run pytest -m contract -q`（`README.md:87-99`）。
- 号码归一化：分隔符无路由含义、缺 `+` 补 `+`（`README.md:80-85`）。

### 4.3 分层现状（引用即受限）

依据 [`../acceptance/test-plan.md`](../acceptance/test-plan.md) L13-22：

- **① 快 `unit or contract`**：有 `.so` 时跑真栈；**S1/S4 走 `accept_all_invites` harness**（旁路 `decide()`），S2/S3 走 `decide()`。
- **② 集成 `integration`**：真栈子集 —— TCP/TLS、FORWARD 双腿、SDP、`test_product_path`（仿真链 + 规则，**无** accept-all）。
- **③ e2e `e2e`**：**0 条**。
- **容量 `performance`**：M6 产品 runtime 压测对端是 **accept-all harness**，**不是业务判决路径**。

> `accept_all_invites` **不是** ims-sim，**也不是**生产路径；REQ-F-1 的 14 条 B2BUA **未**由 harness 签收（`test-plan.md` L22、L30）。

---

## 5. 明确不做清单（N/A 汇总）

| 不做的事 | 一句理由 | 依据 |
|---|---|---|
| 媒体 / RTP / 转码 / DTMF / MRF / 媒体锚定 | 网外媒体中继是三角路由且触及语音合规；放音由网内 MRF 执行，AS 只给判决 | `AGENT.md` §2；ADR-0004 |
| CDR 采集 / 投递 / 归档 / 批价 | 以按 Call-ID 的呼叫轨迹替代话单 | `AGENT.md` §2；ADR-0017 |
| 合法监听（LI） | IRI 属网内网元；第三方 AS 介入引入跨法域暴露 | `AGENT.md` §2；[`../architecture/新系统整体架构.md`](../architecture/新系统整体架构.md) §9.2 |
| Diameter Sh（TS 29.328 / 29.329） | 数据来自自有数据面，不与 HSS 交互 | `AGENT.md` §2；评审 G-P0-4 |
| Diameter Cx（TS 29.228 / 29.229） | Cx 是 HSS↔S-CSCF 内部接口，属运营商网元 | §3.2 |
| 计费（TS 32.260 / 32.299） | 计费数据归属运营商计费域 | ADR-0017 |
| 多租户 | 运营商交付本身是一客户一系统；单租户天然物理隔离 | `AGENT.md` §2 |
| 配置走 GitOps | 不要求运营商运维为改号段学 Git；配置存 PostgreSQL 行 | `AGENT.md` §2；ADR-0006 |
| 写 Operator（CRD） | Helm + 标准 Deployment / ConfigMap / Secret 已足够 | `AGENT.md` §2；ADR-0013 |
| S-SBC 透明桥接 | 运营商侧网元职责，不是我方交付物 | ADR-0003；[`../../testbed/simulators/src/as_simulators/bridge.py`](../../testbed/simulators/src/as_simulators/bridge.py) 仅为仿真 |
| SIP digest 认证（RFC 6733） | 对端准入靠 TLS + 白名单，不靠 digest challenge | §3.7 |
| iFC 触发 / 按号段百分比灰度触发 | 属 S-CSCF/HSS 侧；AS 只实现 ISC 触发后的业务判决 | [`../product-packaging-plan.md`](../product-packaging-plan.md) §1 交付物 2.4；评审 G-P0-5 |

---

## 6. 未决与阻塞

| 项 | 阻塞源 | 影响面 | 何时可闭合 |
|---|---|---|---|
| E1（S1–S11 产品路径真实 socket 对拍） | 未执行；`docs/specs/` 无原文，基线由 sippy 抓取，S7b/S9/S10/S11 缺失 | §3.1 / §3.6 / §4 全节状态上限 | M8 验收（[`../plan.md`](../plan.md) §5.1 O2/O3） |
| E4（S12 TLS 证书热轮换） | 无实验室证据；native TLS S1 曾 503 Certificate Validation Failure | §3.6.7 传输与 TLS、§3.6.8 安全 | M8 验收 + 运营商 PKI（REQ-S-2 / REQ-S-3） |
| E5（状态外置与进程重启恢复） | 默认 DUM 的 UAS 重启测试回 481；无公开 UAS rehydrate API | §3.6.4 / §3.6.6 | 设计缺口评审后；REQ-NF-1 保持硬要求（ADR-0022） |
| TS 24.229 条款级符合性与 Release 适用性 | 仓库内未留存规范原文 | §3.1 全部单元格；所有 release 相关判断 | 人工取回原文逐条核对 |
| GSMA IR.92 / IR.94 | 仓库内未留存原文，无逐条实现证据 | §3.5 整节 | 人工取回原文 + 先裁决哪些条款随「不做媒体」N/A |
| `608 Rejected` 是否要实现 | 文档与代码口径不一致（§3.8） | §3.8、§5 | 新 ADR + 契约变更 + 评审 |
| TCP 端口口径（Dockerfile `5061/tcp` vs values `5061 = TLS`） | 打包口径未对齐 | §3.6.7 | 维护者裁决后修正打包文档 |
| `AS` 是否应插入 Record-Route | 产品代码未显式设置，行为由 DUM 默认决定 | §3.6.3 | 人工核对规范原文 + 与 S-SBC 联调确认 |
| D10 / REQ-F-4 / REQ-S-4 等验收项 | 工程切片 ≠ REQ 验收 | §3.6.3、§3.6.6 | 逐条验收报告 + 维护者签字 |
| ADR-0023（Redis checkpoint）、ADR-0025（管理面编译契约） | 状态仍为 **draft**（[`../architecture/adr/README.md`](../architecture/adr/README.md) L39、L41） | 引用其设计作为证据时 | 评审通过后 |
| O1 容量目标 | 未裁决 | 本文不含容量数字；Datasheet 容量章节（B 类）阻塞 | 维护者裁决 |

---

## 7. 追溯

| 项 | 内容 |
|---|---|
| 对应交付物 | [`../product-packaging-plan.md`](../product-packaging-plan.md) §1 第一批 **1.2（3GPP 规范符合性矩阵）**；A 类（不依赖未决项，见该文档 §3.2） |
| 已落实评审意见 | **G-P0-4** —— Sh 相关面板 / 告警移出范围，合规矩阵中 Sh 标 **N/A**（§3.3；另见计划文档 §1 交付物 2.1 / 2.2 已删除 `sh-interface.json`）<br>**G-P1-6** —— 矩阵注明 **E1/E4/E5 待 M8 验收**、**sippy 仅 testbed 基线**（见状态块与 §3.6.7） |
| 引用的 ADR | ADR-0003（ISC 单一接入语义，accepted）、ADR-0004（媒体 seam，accepted）、ADR-0006（配置治理，accepted）、ADR-0013（Helm-only，accepted）、ADR-0014（分层测试床；testbed 非 v1 交付物）、ADR-0016（边界内安全，accepted）、ADR-0017（不做 CDR，accepted）、**ADR-0019（SIP 栈选型，accepted）**、ADR-0022（DUM 之上产品 CallController，accepted；D10/REQ-NF-1 仍 open）；**ADR-0023、ADR-0025 仍为 draft** |
| 引用的 REQ / 验收项 | REQ-F-1（14 条 B2BUA）、REQ-F-2（两腿 Call-ID）、REQ-F-3（Request-URI）、REQ-F-4（SDP 字节恒等）、REQ-F-5（Route/Record-Route）、REQ-F-6（404）、REQ-F-7（603）、REQ-F-10（非 2xx 分支）、REQ-NF-1（重启不掉呼叫）、REQ-NF-5（ISC 语义）、REQ-S-1/S-2/S-3（peer 白名单 / 运营商 PKI / 证书热轮换）、REQ-NF-13（日志字段契约）；E1 / E4 / E5 仍 open |
| 同批交付物 | [`one-pager.md`](one-pager.md)（1.1）、[`ne-datasheet.md`](ne-datasheet.md)（1.3）、[`responsibility-matrix.md`](responsibility-matrix.md)（3.3）、[`version-lifecycle.md`](version-lifecycle.md)（3.5）、[`security-privacy.md`](security-privacy.md)（3.4）**均已落盘** |
| 状态纪律 | 本文只登记**证据状态**，不构成验收结论；M8 退出签字仍搁置，**RC 就绪 ≠ 通过**（[`../acceptance/report.md`](../acceptance/report.md) §0） |

---

> **维护者评审前，本矩阵的每个 `open` 都不得在对外材料中升级为「符合」**。升级路径只有一条：补齐 **A 级证据**（产品代码 + 对应测试的 `file:line`，或契约场景号），并按 `AGENT.md` §3 走完 requirement → ADR → HLD/LLD → 契约 → 验收 → review record 全链。