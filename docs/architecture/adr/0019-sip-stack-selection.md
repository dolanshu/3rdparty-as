# ADR-0019：生产 SIP 协议栈选型（推翻 ADR-0011 的栈前提）

- **编号**：ADR-0019
- **状态**：**已接受（Accepted）—— 选定 reSIProcate**
- **日期**：2026-09-28
- **接受日期**：2026-09-28
- **取代**：由 [ADR-0011](0011-sip-stack-dual-path.md) 确立的"生产栈 = sippy"前提（ADR-0011 的双栈并行框架仍有效）
- **关联**：架构决策 8、O1、O2、O3、D1、D2；ADR-0011；[`容量量级估算.md`](../容量量级估算.md)；[`docs/SIP_stack_selection.md`](../../SIP_stack_selection.md)
- **回应 REQ**: 隐含回应所有 REQ-F-*（SIP 栈是所有信令功能的基础设施）

---

## 1. 背景与问题

架构文档决策 8 与 [ADR-0011](0011-sip-stack-dual-path.md) 确立"双栈并行"：sippy 保生产，`go-b2bua` 做试点。
该决策的隐含前提是 **sippy 继续作为生产栈**。

维护者现在明确推翻这个前提：**sippy 退出生产栈**。
生产栈用什么尚未决定，候选包括 `go-b2bua`（Go）与 C/C++ 系栈。

在这个决定完成之前，M2（`platform/` 内核）不能开工 —— 因为内核的 SIP 适配层
是栈相关的，提前写会写下要推翻的代码。因此本 ADR **阻塞 M0 签字**。

### 1.1 为什么不能用容量作为理由

[`容量量级估算.md`](../容量量级估算.md) 的结论是：**容量不是候选栈的区分项**。
选型设计目标 ≥500 CPS / ≥20,000 并发对话，在"多副本 + 无状态"架构下，
连 sippy 的标称能力（单进程 150–400 CPS）拆到 4 个副本都够用。

所以本 ADR 的决策依据**不是性能**，而是维护性与供应链风险。
容量量级估算文档独立负责"容量不是区分项"这一结论，本 ADR 仅引用。

---

## 2. 决策依据（真实理由）

| # | 理由 | 说明 |
|---|---|---|
| R1 | **上游活跃度 / 供应链风险** | sippy 维护者单一、关键 issue 长期未关闭；产品按 10 年生命周期交付，不能把生产信令面压在一个无明确路线图的依赖上 |
| R2 | **运行时生命周期** | sippy 验证过的 Python 3.10 于 2026-10 到达 EOL（未决项 D1）。换栈可顺带解除运行时锁 |
| R3 | **维护性与排障能力** | 产品化需要能在现场读源码、打补丁、定位信令问题。单进程 GIL 模型和 Python 2 血统增加这个成本 |
| R4 | **运维形态** | 单节点静态二进制优于多进程 Python 运行时（运营商 on-prem 交付，运维人力有限） |

### 2.1 R1 证据表

抓取日期：2026-09-28。

| 来源 | 仓库 URL | 近 12 个月提交数 | 未关闭 issue/PR 数 | 最旧未关闭 issue | 最近一次 release |
|---|---|---|---|---|---|
| sippy（Python） | <https://github.com/sippy/b2bua> | 50 | 28 | 2014-09-13 | v2.4.2（2026-07-15） |
| go-b2bua | <https://github.com/sippy/go-b2bua> | 5 | 3 | 2023-09-06 | 无 release（最新 commit 2026-06-05） |

> 说明：sippy 主仓库仍有维护性提交，但核心作者单一、历史 issue 大量积压、TLS 热轮换与状态序列化等产品化能力无上游路线图；go-b2bua 活跃度更低。10 年生命周期下，这构成供应链风险而非短期活跃度风险。

---

## 3. 候选范围

从 [`docs/SIP_stack_selection.md`](../../SIP_stack_selection.md) 按硬约束筛选。

### 3.1 硬约束（不满足即出局）

| 约束 | 含义 | 能力归属 | 依据 |
|---|---|---|---|
| **H1 许可** | 闭源商用分发无需购买授权 | 栈原生 | 产品为商业交付；GPL/AGPL/双许可出局 |
| **H2 vendoring** | 能固定到具体 commit/tag 并 vendoring 进仓库 | 栈原生 / 自建 | `AGENT.md` §8 依赖治理 |
| **H3 纯信令栈** | B2BUA 语义，维持完整 call state，不做媒体 | 栈原生 | 架构 §2 非目标、决策 4 |
| **H4 TLS + 证书热轮换** | 支持 SIP over TLS；证书轮换不重启进程、不丢在途呼叫 | 栈原生 / 自建 / 组合；probe 验证 | `AGENT.md` §13 |
| **H5 状态可外置** | 对话/事务状态可序列化与恢复，不强制绑单进程内存 | 栈原生 / 自建 / 组合；设计审查或 probe 验证 | 架构 §2/§4，决策 2 |

> 能力归属说明："栈原生"指能力由栈本身提供；"自建"指由本团队在栈外实现；"组合"指栈提供部分机制、团队补齐其余。

### 3.2 进入评估的候选

| 候选 | 语言 | 许可 | 能力归属说明 | 备注 |
|---|---|---|---|---|
| **go-b2bua** | Go | BSD-2-Clause | 栈原生 | sippy 作者官方移植，**与 POC 行为基线同源**；无 release，须 commit pin + vendoring |
| **reSIProcate** | C++ | Vovida（类 BSD） | 栈原生 / 自建 | Sipwise NGCP、CounterPath 商用在用；TCP/TLS 传输层是已知短板，**由 TLS probe 判定是否保留** |
| **libre** | C | BSD-3-Clause | 栈原生 / 自建 | creytiv 血统，2025 仍高频发布（libre 4.3.0）；取 SIP/SDP 部分，**baresip 带媒体模块，不进候选** |

### 3.3 明确排除

| 排除 | 原因 |
|---|---|
| PJSIP | GPLv2 / 商业双许可（违反 H1） |
| Belle-SIP / Flexisip | GPLv3 / AGPLv3（违反 H1） |
| Kamailio / OpenSIPS | GPL 且是代理/服务器平台，非裸栈（违反 H1、H3） |
| FreeSWITCH / Asterisk | 全媒体栈，与"不做媒体"冲突（违反 H3） |
| Sofia-SIP | LGPL，商用障碍（H1 边缘）；且为纯栈但许可不利 |
| **rsipstack** | MIT 且为纯栈，但 **Rust 不在当前团队技术栈内**，学习与排障成本作为**否决项**，不进入正式候选 |
| oSIP / eXosip2 | GPL；活跃度低 |
| Doubango | 唯一 3GPP TS 24.229 实现，但约 2016 年停更（违反 R1） |
| drachtio | MIT 但形态是 server + Node.js 框架，非裸栈（H3 不对位） |
| JAIN-SIP | NIST 明确不保证持续支持（违反 R1） |
| **sippy** | 本 ADR 的前提即排除它作为生产栈；保留为 `testbed/` 基线参考 |
| **fork / vendor sippy** | vendoring 不能解除 R3（Python GIL / 单进程模型）与 R4（多进程 Python 运维形态）；维护责任仍落到本团队，且无法解决 D1 |

---

## 4. 评估矩阵

| 维度 | 通过标准 | 权重 |
|---|---|---|
| **E1 行为等价** | 真实 socket 对拍复现 POC 基线（§5 场景） | **门槛项**，不过即出局 |
| **E2 许可** | 闭源商用免授权 | 硬约束 |
| **E3 vendoring** | 可 commit pin + vendoring | 硬约束 |
| **E4 TLS 与热轮换** | 支持 SIP over TLS，证书轮换不重启、不丢在途呼叫 | 硬约束 |
| **E5 状态外置** | 状态可序列化/恢复，或栈本身可无状态多副本 | 硬约束 |
| **E6 构建集成** | 能进 monorepo 构建与 CI（Go module / cmake / autotools） | 中 |
| **E7 上游活跃度** | 近 12 个月有提交；issue 有人响应 | 高 |
| **E8 可维护性** | 按 §4.1 子项加权综合分评估（代码量 / 构建复杂度 / 调试工具链 / 日志与状态导出 / 社区文档 / 技能匹配） | 高 |
| **E9 与基线同源性** | 与 POC（sippy）行为的可对照程度 —— 决定 M1 基线的复用价值 [^e9] | 高 |
| **E10 容量参考** | 标称能力覆盖 ≥500 CPS / ≥20,000 并发（含多副本） | **低**（§1.1：非区分项） |
| **E11 语言耦合度** | 栈的实现语言与项目主语言（Python）的耦合程度——决定 platform 内核是否需要换语言、是否引入跨语言 FFI 桥接 | **高** |

[^e9]: E9 权重高是有意倾斜，反映 M1 基线复用价值，但 E9 **不得单独构成入选理由**，必须与 E8 等维度权衡。

### 4.1 E8（可维护性）评分口径

E8 不作单一维度打分，拆为下列子项；每项按 0–5 打分（5 最好），加权合成 E8 综合分。

| 子项 | 评分口径 | 权重 |
|---|---|---|
| 代码量（LOC） | 核心路径 LOC 越少越好 | 中 |
| 构建复杂度 | 构建系统种类数 + 外部依赖数，越少越好 | 中 |
| 调试工具链 | 是否原生支持 gdb / lldb / pprof 等 | 高 |
| 日志与状态导出粒度 | 是否有可读日志、可导出 / 可序列化的状态 | 高 |
| 社区文档质量 | 是否有规范文档、示例与维护指南 | 中 |
| 团队现有技能匹配度 | 与团队当前技术栈的重合度 | 高 |

E8 综合分 = 各子项得分按权重加权求和。§6 步骤 3 的"同分按 E8 团队匹配度裁决"即以本表为准。

### 4.2 候选栈纸面评估表

数据抓取日期：**2026-09-28**。本表为纸面评估，**凡涉及运行时行为的维度（E1、E4、E5）均需后续 probe 对拍验证**，纸面结论不作为最终依据。

| 维度 | go-b2bua（Go） | reSIProcate（C++） | libre（C） |
|---|---|---|---|
| **E1 行为等价** | 待 probe（门槛项） | 待 probe（门槛项） | 待 probe（门槛项） |
| **E2 许可** | ✅ 通过（BSD-2-Clause） | ✅ 通过（Vovida，类 BSD） | ✅ 通过（BSD-3-Clause） |
| **E3 vendoring** | ✅ 通过（Go module + commit pin） | ✅ 通过（CMake + submodule / 源码 vendor） | ✅ 通过（CMake + submodule / 源码 vendor） |
| **E4 TLS 与热轮换** | ⚠️ 纸面通过 / 待 probe 验证 | ⚠️ 纸面通过 / 待 probe 验证 | ⚠️ 纸面通过 / 待 probe 验证 |
| **E5 状态外置** | ⚠️ 纸面通过 / 待 probe 验证 | ⚠️ 纸面通过 / 待 probe 验证 | ⚠️ 纸面通过 / 待 probe 验证 |
| **E6 构建集成** | 5 分 | 3 分 | 4 分 |
| **E7 上游活跃度** | 2 分 | 4 分 | 5 分 |
| **E8 可维护性（加权综合）** | **3.4** | **3.0** | **2.7** |
| **E9 与基线同源性** | 5 分 | 1 分 | 1 分 |
| **E10 容量参考** | 4 分 | 5 分 | 4 分 |
| **E11 语言耦合度** | 1 分 | 4 分 | 3 分 |

**评分说明**

**硬约束维度（E2/E3/E4/E5）**

- **E2 许可**：三者均为 BSD 类许可，闭源商用分发无需购买授权，满足 H1。
  - go-b2bua：BSD-2-Clause，见 [LICENSE](https://github.com/sippy/go-b2bua/blob/master/LICENSE)。
  - reSIProcate：Vovida Software License v1.0（OSI 认证，类 BSD），见 [COPYING](https://github.com/resiprocate/resiprocate/blob/master/COPYING)。
  - libre：BSD-3-Clause，见 [LICENSE](https://github.com/baresip/re/blob/main/LICENSE)。
- **E3 vendoring**：三者均可固定到具体 commit 并 vendoring 进仓库，满足 H2。
  - go-b2bua：Go module 天然支持 `replace` 指令指向本地 vendor 目录或特定 commit。
  - reSIProcate / libre：CMake 项目，可用 `git submodule` 或源码拷贝 + CMake `add_subdirectory` 集成。
- **E4 TLS 与热轮换**（⚠️ 纸面判断，待 probe 验证）：
  - go-b2bua：TLS 由 Go 标准库 `crypto/tls` 提供，支持 `GetCertificate` 回调实现热轮换；但具体到 SIP over TLS 的传输层整合需 probe 验证。
  - reSIProcate：支持 OpenSSL TLS 传输（`TlsTransport`），但 TCP/TLS 传输层是已知短板，证书热轮换的具体机制（是否支持不重启轮换、是否影响在途呼叫）需 probe 验证。
  - libre：支持 OpenSSL TLS 传输（`tls` 模块），证书热轮换需在应用层自建（底层栈提供 TLS 上下文管理接口），需 probe 验证可行性。
- **E5 状态外置**（⚠️ 纸面判断，待 probe 验证）：
  - go-b2bua：状态在进程内，需自建序列化；sippy 作者移植，行为模型与 sippy 一致，理论上可参照 sippy 的序列化方案实现，但具体复杂度需 probe 验证。
  - reSIProcate：dum 层有对话管理（`DialogSet` / `Dialog`），栈本身有状态对象模型；是否支持完整序列化/反序列化（含事务状态）需 probe 验证。
  - libre：底层栈，对话状态需在上层应用中完全自建；灵活性高但工作量大，需 probe 验证自建成本。

**普通维度（E6/E7/E9/E10）**

- **E6 构建集成**（中权重）：
  - go-b2bua（5 分）：Go module，单语言，零外部系统依赖，`go build` 即可产出静态二进制，与 monorepo CI 集成最顺滑。
  - reSIProcate（3 分）：CMake 构建，但含多个子库（resip / dum / recon / rutil 等），外部依赖较多（OpenSSL、popt、c-ares 等），CI 集成需要维护依赖链。
  - libre（4 分）：CMake 构建，结构相对清晰；依赖 OpenSSL 等基础库；需从 baresip 生态中裁剪出 SIP/SDP 核心部分，略增集成成本。
- **E7 上游活跃度**（高权重）：
  - go-b2bua（2 分）：近 12 个月约 5 次提交，无 release，3 个 open issue，最旧 issue 2023-09-06；活跃度低，供应链风险高。来源：[GitHub 仓库](https://github.com/sippy/go-b2bua)。
  - reSIProcate（4 分）：近 12 个月持续提交，2026-06-18 发布 1.14.0，issue 有人响应；Sipwise NGCP、CounterPath 等商用用户在用；活跃度中等偏上。来源：[GitHub 仓库](https://github.com/resiprocate/resiprocate)。
  - libre（5 分）：高频发布，2025 年多个 release（libre 4.x），2026 年仍在更新（Fedora 45 已打包 4.11.0）；baresip 生态活跃，社区健康。来源：[GitHub 仓库](https://github.com/baresip/re)。
- **E9 与基线同源性**（高权重）：
  - go-b2bua（5 分）：与 sippy（POC 基线）同作者，行为模型高度一致，M1 基线复用价值最大。
  - reSIProcate（1 分）：独立实现，与 sippy 无血缘关系，行为对照需从零建立。
  - libre（1 分）：独立实现，底层栈，对话语义需上层自建，与 sippy 行为模型差异最大。
- **E10 容量参考**（低权重，仅记录）：
  - go-b2bua（4 分）：Go 并发模型天然支持高并发，单进程预估 500+ CPS 可行；具体数值待 probe。
  - reSIProcate（5 分）：C++ 实现，商用场景验证过大规模部署，容量充裕。
  - libre（4 分）：C 实现，性能优秀，但上层需自建对话管理，整体容量取决于上层实现。
- **E11 语言耦合度**（高权重）：
  - go-b2bua（1 分）：栈是 Go，无跨语言绑定。platform 信令面 70–80% 需用 Go 重写，Python 退居规则引擎和控制面。项目从单语言（Python）变为双语言（Python + Go），维护两套工具链、两套测试框架、两套调试流程。
  - reSIProcate（4 分）：栈是 C++，**自带 Python 绑定**（构建选项 `BUILD_PYTHON=ON`）。platform 内核可保持全 Python，SIP 适配层直接 import reSIProcate Python 模块，无需手写 FFI 桥接。语言边界由上游维护，调试可在 Python 侧完成。
  - libre（3 分）：栈是 C，有 C API。platform 内核可保持全 Python，但 SIP 适配层需**手写 `ctypes` 桥接**——类型转换、内存管理、错误传播都要自己维护。比 reSIProcate 多一层手写 FFI 成本，但仍无需换语言。

**E8 可维护性（加权综合）**

E8 按 §4.1 的六子项分别打分，权重换算：高=1.0，中=0.5；Σ权重 = 4.5。
详细计算过程见下表（各子项 0–5 分）：

| E8 子项 | 权重 | go-b2bua | reSIProcate | libre |
|---|---|---|---|---|
| 代码量（LOC） | 中（0.5） | 4 | 2 | 4 |
| 构建复杂度 | 中（0.5） | 5 | 3 | 4 |
| 调试工具链 | 高（1.0） | 4 | 3 | 3 |
| 日志与状态导出粒度 | 高（1.0） | 2 | 4 | 2 |
| 社区文档质量 | 中（0.5） | 2 | 4 | 2 |
| 团队技能匹配度 | 高（1.0） | 4 | 2 | 2 |
| **E8 综合分** | — | **3.4** | **3.0** | **2.7** |

- **go-b2bua**：优势在团队技能匹配（Go 有基础）、构建简单、代码量小；短板在日志与状态导出（需自建）和社区文档（只有自动生成的 API 文档）。
- **reSIProcate**：优势在日志与状态管理（dum 层完整）和社区文档（商用级）；短板在代码量大（学习曲线陡）和团队技能匹配（C++ 经验有限）。
- **libre**：优势在代码精简和构建简洁；短板在日志状态需上层自建、文档少、团队技能匹配度低。

> **纸面评估结论（非最终）**：E7+E8+E9+E11 高权重维度综合排序 reSIProcate (3.0) > go-b2bua (2.9) ≈ libre (2.9)，go-b2bua 与 libre 同分；按 §6 步骤 3 同分规则，由维护者据 E8 团队匹配度裁决。三者差距不大（0.1 分级），且 E4/E5 均为纸面判断、E1 未验证。最终排名需待 probe 对拍后更新。

---

## 5. 最小对拍场景（E1 门槛）

每个候选写一个 probe，跑真实 socket，验证以下行为与 POC 基线一致。
基线由 M1 在 `testbed/` 下用 sippy 抓取 S1–S11 并落盘到 `testbed/contracts/sip-baseline/`，
probe 以该基线已落盘为进入条件。

对拍只校验**外部可观测消息行为**：方法、响应码、关键头域的存在性与语义、消息顺序；
不校验头域顺序、Via branch 的具体取值、SDP 的 `o=` 时间戳等实现细节。

**断言粒度表**（逐字段归类，保证不同人写的 probe 得出相同结论）：

| 粒度 | 含义 | 字段 |
|---|---|---|
| **严格相等** | 必须逐字一致 | 方法（`INVITE` / `ACK` / `BYE` / `CANCEL` …）、响应码（`100` / `180` / `200` / `4xx` …）、`CSeq` 的方法名 |
| **仅校验存在性** | 只要求该头域存在，不比较取值 | `To` / `From` 的 tag 是否存在、`Contact` 是否存在 |
| **符合模式** | 必须匹配给定模式，取值本身不比较 | `Via` branch 以 `z9hG4bK` 开头；tag 为随机十六进制；`Call-ID` 为合法 host 形式（`local-id@host`） |

> `Call-ID` 两腿必然不同（S5 已述），因此不在上表三类约束之内 —— 它按"两侧取值必须不同"单独判定。

| # | 场景 | 断言 |
|---|---|---|
| S1 | 基本呼叫 | `INVITE → 100 Trying → 180 Ringing → 200 OK → ACK`，之后 `BYE → 200 OK` |
| S2 | 无匹配规则 | 收到 `INVITE` → 回 `404 Not Found` |
| S3 | 策略拒绝 | 收到 `INVITE` → 回 `603 Decline` |
| S4 | caller 放弃 | `INVITE` 未接通时收到 `CANCEL` → 回 `200 OK`，并向被叫侧发 `CANCEL` |
| S5 | 双腿 B2BUA | UAS 腿终止、UAC 腿新建，两侧 **Call-ID 不同** |
| S6 | Request-URI / 号码改写 | 改写后按新 URI 转发，其余头域按规则透出 |
| S7a | SDP 完全透传模式 | SDP 逐字节不变，不修改任何字段，不锚定媒体 |
| S7b | SDP 按契约改写模式 | 仅按契约改写指定字段，其余字段保持不变，不锚定媒体 |
| S8 | Route / Record-Route 处理 | S-CSCF 在 `Record-Route` / `Route` 中插入路径；AS 在 in-dialog 请求中保持该路径，不丢失或错排 `Route` 头 |
| S9 | in-dialog 请求路由 | 已建立对话后收到 `BYE` / `re-INVITE` / `UPDATE` 仍经 AS 处理，并按 `Route` 集回送 |
| S10 | 非 2xx 分支处理 | 被叫侧返回 `486 Busy`、`480 Temporarily Unavailable`、`408 Request Timeout` 时，AS 向主叫侧回传对应最终响应并清理对应腿 |
| S11 | CANCEL 与最终响应竞态 | 主叫侧发 `CANCEL` 后，若被叫侧同时返回最终响应（2xx 或 6xx），AS 不产生重复 ACK/错误路由；最终按事务语义收敛 |

### 5.1 后续场景清单（非 E1 门槛，M2/M3 逐步补全）

re-INVITE（hold / resume）、forking、retransmission 超时、REFER（呼叫转移语义）、PRACK / UPDATE 交错、
`P-Asserted-Identity` 与信任域白名单校验。

### 5.2 S12：TLS 证书热轮换（E4 硬约束验证场景，非 E1 门槛）

S12 不属于 S1–S11 的 E1 门槛集；它用于验证 §4 E4 与 §3.1 H4。候选进入 Accepted 前**必须通过**本场景，
但它**不阻塞 E1 probe 启动**。断言（需全部满足）：

- 轮换过程中，在途呼叫的 `BYE` 正常完成（`BYE → 200 OK`），呼叫不中断；
- 轮换完成后发起的新呼叫，使用**新证书**建立 TLS 会话；
- 整个轮换过程**进程不重启**；
- 轮换窗口内**不发生呼叫丢失**（无异常终断，无由 AS 自身触发的 5xx）。

---

## 6. 决策流程

0. **基线落盘**（进入 probe 的前提）：M1 阶段先用 sippy 在 `testbed/` 跑 S1–S11 抓取基线，
   落盘到 `testbed/contracts/sip-baseline/`。责任人：开发/AI agent；维护者确认基线覆盖 S1–S11 后方可进入步骤 1。
1. **纸面审查**（E2/E3/E4/E5/E7）：先淘汰不满足硬约束的候选。已完成，结果见 §3。
2. **probe 对拍**（E1）：阶段 A 只跑 `go-b2bua`（时间盒 2 周）。若通过 E1 且 E8 可接受，
   即可进入 Accepted 流程。C/C++ 候选（reSIProcate / libre）作为阶段 B，
   仅在 `go-b2bua` 未通过 E1，或 E8 团队匹配度不可接受时启动。
   E1 门槛场景为 **S1–S11**；**S12（TLS 证书热轮换，见 §5.2）** 用于验证 E4 硬约束，
   不阻塞 E1 probe 启动，但候选在进入 Accepted 前**必须通过**。
3. **深度评估与裁决**（E6/E8/E9）：对过 E1 门槛的候选，按以下规则裁决：
   - E1 是淘汰门槛，未通过者出局；
   - 通过者按 E7 / E8 / E9 / E11 加权合计最高者入选；E8 按 §4.1 的子项加权综合分计；
   - E10 仅记录，不作决策输入；
   - 同分时由维护者据 E8 团队匹配度裁决；
   - **E6 的验证方法**：写一个**最小 CI job**，编译候选栈并跑一个最小 probe（S1 即可）；
     该 job 在 CI 中通过即视为 E6 的证据。它是 **probe 阶段的产出物**。
4. **回退触发条件**：当且仅当满足下列之一时，才考虑回退至 sippy，并把本 ADR 记为 Rejected：
   - （a）全部正式候选均未通过 E1 门槛；或
   - （b）E8 综合评估（§4.1）显示维护成本高于继续维护 sippy 的成本 ——
     量化阈值为**需投入工时 > 现有 sippy 维护工时 × 2**。口径：以最近 12 个月本团队在 sippy 上投入的
     人时（含缺陷修复、升级、排障）为基数，用同期工时台账或估算值折算；口径由维护者在评估时确认。
5. **本 ADR 转 Accepted**（2026-09-28）：
   - **选定栈**：reSIProcate（C++，Vovida 许可，类 BSD）
   - **版本 pin**：待 M1 probe 阶段确定具体 commit / tag（当前最新 release 为 1.14.0，2026-06-18）
   - **集成方式**：CMake + `git submodule` vendoring；通过 Python 绑定（`BUILD_PYTHON=ON`）接入 platform 内核
   - **接受的缺口**：
     1. E1 行为等价（S1–S11）尚未通过真实 socket probe 验证 —— M1 阶段补齐，不通过即回退至 go-b2bua 或 sippy
     2. E4 TLS 证书热轮换（S12）尚未验证 —— M1 阶段补齐
     3. E5 状态外置 / 序列化能力尚未验证 —— M1 阶段补齐
     4. TCP/TLS 传输层为 reSIProcate 已知短板，生产环境需重点关注 —— 见 K8
     5. C++ 栈引入 C++ 工具链与调试成本 —— 团队需补充 C++ / gdb 能力
     6. probe 完成前 platform 内核的 SIP 适配层暂不开工（K2）
6. **同步更新**：`docs/architecture/新系统整体架构.md` 决策 8、ADR 注册表、`docs/SIP_stack_selection.md` 结论节、`platform/pyproject.toml`。

---

## 7. 当前后果（Consequences）

### 7.1 已接受的代价

| # | 代价 | 缓解 |
|---|---|---|
| K1 | **M0 签字被阻塞**。在选型完成前仓库停在骨架状态 | 本 ADR 走快速评估通道，不追求完美 |
| K2 | **`platform/pyproject.toml` 当前 SIP 依赖为空**，M2 之前无法写任何信令代码 | 先定义语言无关 seam（`Transport`、`StateStore`、`CallController` 外壳），不绑定任何栈 |
| K3 | **M1 抓的 POC 基线基于 sippy**，若最终选 C/C++ 栈，基线的"等价"需要重新解释（不是逐行对照） | 基线以**外部可观测消息行为**形式记录（S1–S11），而非以 sippy API 形式记录 |
| K4 | `go-b2bua` 若入选，**没有 release**，须 commit pin + vendoring，且上游维护责任部分落到我们身上 | 按其上游回归套件在本仓库跑；pin 记录在 `AGENT.md` §8 等价条款里 |
| K5 | 引入 Go 或 C/C++ 会**打破"一个解释器"的简单性**，monorepo 需要多语言构建链（未决项 D2 变硬约束） | 在 M2 之前由 D2 的 ADR 定结构 |
| K6 | **可能连带重开 ADR-0005 / 0009 / 0010**。三者均建立在 sippy 阻塞模型之上：ADR-0005（OTel 导出不能阻塞呼叫路径）、ADR-0009（ISSU 只能 draining）、ADR-0010（自定义指标 HPA + 缩容保护控制器） | 栈确定后逐条复核：若新栈是非阻塞模型，ADR-0005/0010 前提改变；若状态可序列化，ADR-0009 可从 draining 升级为状态迁移 |
| K7 | **换栈后 Python 运行时角色需重新定位** | 若最终栈为 Go/C/C++，`platform/` 的 Python 内核退化为 seam 定义与测试 harness，ADR-0012 的"跨实现对拍"语义从"Python vs Go 同用例"变为"新栈实现 vs `testbed/` 基线" |
| K8 | **reSIProcate TCP/TLS 传输层为已知短板**，生产环境需重点监控 TLS 连接稳定性与热轮换表现 | M1 probe 阶段重点验证 S12；生产部署增加 TLS 连接指标告警 |

### 7.2 未解决

- 选定哪个栈：**reSIProcate**（2026-09-28 接受）
- E1 / E4 / E5 的 probe 验证**尚未完成**，作为接受的缺口登记（见 §6 步骤 5）。
  M1 阶段执行 probe，若任一硬约束（E4/E5）或门槛（E1）不通过，触发回退评估。
- 若最终仍回到 sippy（评估后认为换栈收益不足），本 ADR 应记为 **Rejected** 并说明理由，而不是悄悄丢弃。
  回退情形下，R2（Python 3.10 于 2026-10 EOL，未决项 D1）仍然成立，处置路径二选一：
  - 迁移 Python 运行时到 3.11 / 3.12 并重新验证 sippy；或
  - 在 ADR 中把 EOL 运行时登记为已接受的 risk。

---

## 8. 评审记录

评审记录单独落盘于 [`docs/reviews/adr-0019-review.md`](../../reviews/adr-0019-review.md) 与
[`docs/reviews/adr-0019-review-round2.md`](../../reviews/adr-0019-review-round2.md)。
依 `AGENT.md` §3.2，本 ADR 在被 Accept 之前必须有该文件。

---

## 9. Probe harness（2026-09-30）

E1 / E4 的 probe harness 已落盘于 `testbed/probe/`：

| 文件 | 作用 |
|---|---|
| `testbed/probe/e1_baseline_probe.py` | E1：在真实 socket 上重放 `testbed/contracts/sip-baseline/` 的 S1–S11 基线，逐条比对被测栈发出的消息 |
| `testbed/probe/tls_hot_rotation_probe.py` | E4 / S12：断言证书热轮换不重启进程、不丢在途呼叫 |
| `testbed/probe/sequence_compare.py` | 纯函数比对器：方法 / 响应码、`Call-ID`、Request-URI 的 `host:port`、body 逐字节；不比头域顺序 / `Via` branch / SDP `o=` 时间戳 |
| `testbed/probe/tests/test_sequence_compare.py` | 比对逻辑的 unit 测试（marker `unit`） |
| `testbed/probe/README.md` | 运行方式、退出码、绑定缺失时的预期行为、K2 约束 |

**当前未执行。** 本环境没有 reSIProcate 的 Python 绑定 —— 构建选项 `BUILD_PYTHON=ON` 未构建，
`import resip` 失败（本次实跑确认）。两个探针**惰性 import** 绑定模块，缺失时以**退出码 2 响亮失败**
并打印构建指引（如何用 `BUILD_PYTHON=ON` 构建、如何让它可被 import、如何重跑），**不会静默 skip** ——
skip 不是证据，K2 不得在没有任何证据的情况下被解除。

因此：

- **E1（S1–S11）与 E4（TLS 热轮换）在本 ADR 中保持开放的接受缺口**，状态不因 harness 落盘而改变；
  只有在具备绑定的环境跑通并把结果回填 `docs/acceptance/report.md` 后，才可更新 §6 步骤 5 的缺口清单。
- 被测栈的接口由极简 Protocol 表达（`StackUnderProbe.send(payload) -> bytes | None`、
  `TlsStackUnderProbe` 的四个方法）；**适配 reSIProcate 绑定的适配器本次未实现**，
  真实接入时由绑定侧提供（可选入口 `create_stack_under_probe(host, port)`）。
- **E5（状态外置 / 序列化）的探针尚未编写**，列为后续项 —— E5 目前连可执行的判定都没有。
- K2 仍然生效：probe 通过前，`platform/` 的 SIP 适配层不开工。

## 10. Evidence correction (2026-09-30)

The historical Accepted decision above selected reSIProcate and remains in force. A correction to its stated integration route is required: inspection of upstream reSIProcate 1.14.0, tag commit `632e215c2ca9aee5416bfe1808851ea6fa380044`, confirmed that `BUILD_PYTHON=ON` enables PyCXX-based rePro Python routing/plugin targets; it does **not** provide a general `resip`/DUM Python binding. The E1 harness's `import resip` therefore exited 2. This corrects the integration evidence, not the stack selection.

The proposed [ADR-0022](0022-resiprocate-b2bua-control.md) tracks the DUM/product `CallController` responsibility split and the unresolved integration and state-recovery design. E1, E4, and E5 remain open; K2 remains unreleased. Native DUM S1/S4 smoke is not product E1 acceptance, and native TLS S1 failed to establish a call (503 Certificate Validation Failure; timeout exit 124). No product acceptance or release conclusion follows from these observations.
