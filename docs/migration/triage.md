# 迁移甄别（Migration triage）— POC 代码如何进入本仓库

**绝不整块照搬。** POC（`3rtparty_AS_POC`，约 24 kLOC，含测试与工具）和抽出来的库
（`as_platform`，约 4.2 kLOC）是为验证概念而建的，处于一套本产品明确不共享的非目标之下：
无 HA、无持久化、无容量目标、无受管配置。因为"文件存在就采纳"，正是产品连同代码一起继承那些
非目标的方式。

每个越界的文件都要先甄别。甄别的产出是逐文件的裁决，且要有证据。

## 1. 顺序 —— 在碰任何东西之前先快照

1. **冻结 POC。** 记下本次甄别所基于的 `3rtparty_AS_POC` 与 `as_platform` 的 commit。
   在构建产品期间 POC 不变；如果必须变，受影响的文件要重跑甄别。
   - 冻结点（维护者批准，2026-09-27）：`3rtparty_AS_POC` @ `4ddf3df332f950ea41d261274dfa1178a0930de4`（`as_platform` 的提交包含在该仓库历史中）。M1 期间 POC 不变；如果必须变，受影响文件重跑甄别。
2. **抓取行为基线。** 在重写任何文件之前，抓取 POC 实际做了什么：真实消息样例、端到端呼叫
   trace、代码所依赖的观察到的 sippy 行为。重写只允许对着这个基线声称"等价"，绝不对着记忆。
3. **清点并分类** 每个文件，用 §3。
4. **只有到那时** 才把代码写进 `platform/`、`apps/`、`services/`、`testbed/`。

第 1、2 步不是可选项。没有基线，"重写后行为相同"就是一个谁都无法核查的断言。

## 2. 四种裁决

| 裁决 | 含义 | 举证责任 |
|---|---|---|
| **A — 采纳（adopt）** | 文件符合目标架构，且其行为已被测试验证 | 现有测试必须原样在这里通过，或重写以证明同一行为 |
| **B — 重写、保留概念** | 想法存活；实现违反了产品约束（有状态、阻塞、无版本化、无审计） | 指明约束以及施加它的 ADR |
| **C — 仅作基线参考** | 代码不采纳。读它是为了恢复必须被复现的行为 | 恢复出的行为必须变成契约用例或测试 |
| **D — 丢弃（discard）** | 没有可带过来的东西 | 一句话说明原因 |

没有裁决的文件不迁移。没有证据的裁决不算裁决。

## 3. 清点与初步分类

规模为甄别时实测。**分类列是初步提议**，源自 POC 的 `AGENT.md`、它的 ADR 以及
[`../architecture/新系统整体架构.md`](../architecture/新系统整体架构.md) —— 它不是逐文件的评审。
每一行在 M1 中确认或推翻，这正是 M1 不写产品代码的原因。

### `as_platform/` → `platform/`（约 4.2 kLOC）

| 文件 | LOC | 裁决 | 原因 |
|---|---|---|---|
| `call_controller.py` | 1030 | C | B2BUA 状态机是对 sippy 与进程内状态最深的耦合。§6.2 直言 sippy 的事务状态无法序列化或迁移，所以产品的 draining 模型必须绕着它建，而不是建在它之上。先恢复行为，再重写。 |
| `internal_api.py` | 497 | B | 表面变成 ADR-0012 中的语言无关契约（`/healthz`、`/metrics`、`/traces`）。形状存活，载荷不存活。 |
| `observability/tracing.py` | 347 | B | 呼叫轨迹变成可按 Call-ID 查询的产品能力，带保留期（ADR-0005）；进程内 ring 不存活。 |
| `state_store.py` | 334 | B | `StateStore` seam 是对的，留着。`InMemoryStateStore` 不留：§7 要求 Redis 加 Sentinel，且 ADR-0002 禁止每进程会话状态。 |
| `main.py` | 357 | B | 进程壳存活；它获得 draining、版本上报、非阻塞导出（ADR-0009、ADR-0005）。 |
| `transport.py` | 239 | B | UDP 加一个只到监听侧的 `TlsTransport`。ADR-0016 要求端到端 TLS 加轮换，且不能重启进程。 |
| `observability/logging.py` | 193 | B | 结构化字段存活；emitter 换成 OTel logs。 |
| `observability/metrics.py` | 179 | B | `MetricsRegistry` 是进程内视图，在 N 个副本之后无意义。获得 `active_calls` 与 `cps`，HPA 也要（ADR-0010）。 |
| `capacity_harness.py` | 195 | C | 驱动回调而非 socket。ADR-0014：绕过 socket 与事件循环的 harness 测的是业务逻辑，不是容量。 |
| `errors.py` | 163 | A | 基于每族子类的、无成员的 `ErrorCode` 机制，正是产品想要的形态。 |
| `sip_adapter.py` | 244 | B | 把 sippy 限制在一个模块内，完全正确。对着双栈决策重新论证（ADR-0011）。 |
| `bootstrap.py` | 111 | B | 启动自检存活并扩展（状态存储可达性、规则版本）。 |
| `version.py` | 102 | D | 每组件版本文件正是 ADR-0018 要消灭的漂移。 |
| `route_header.py` | 84 | A | 小、源自 RFC、可测试。对着观察到的行为验证。 |
| `hop.py` | 53 | A | `NextHop` 值对象，没有产品约束碰到它。 |
| `observability/__init__.py` | 21 | A | — |
| `__init__.py` | 59 | B | 只做再导出；为新的包表面重建。 |

### `src/as_app/` → `apps/translation/`（约 2.3 kLOC）

| 文件 | LOC | 裁决 | 原因 |
|---|---|---|---|
| `call_controller.py` | 527 | C | 内核状态机之上的薄胶水；随内核一起重写。 |
| `internal_api.py` | 388 | B | 见内核 `internal_api.py`。 |
| `main.py` | 331 | B | 一个用例的进程壳。 |
| `routing/rules.py` | 371 | B | 加载与热重载是对的；事实源移到 config-service，带版本与兼容矩阵（ADR-0006、R4）。 |
| `routing/engine.py` | 220 | **A** | 纯函数，无 socket、无时钟 —— 正是强制 TDD 的形态。带着它的测试采纳。 |
| `bootstrap.py` | 164 | B | 见内核 `bootstrap.py`。 |
| `observability/*` | ~147 | D | 仅为桥接两个仓库而存在的再导出门面。monorepo 让它们失去意义。 |
| `errors.py` | 63 | A | `AS-RULE-*` / `AS-ROUTE-*` 族。 |
| `route_header.py` | 61 | D | 重复内核的；只留一份。 |
| `sip_adapter.py` | 47 | D | 再导出门面，同 `observability/*` 的原因。 |
| `__init__.py` | 84 | B | — |

### `src/anti_fraud_as/` → `apps/anti-fraud/`（约 2.6 kLOC）

| 文件 | LOC | 裁决 | 原因 |
|---|---|---|---|
| `call_controller.py` | 601 | C | 判决 seam 概念是对的；腿处理随内核重写。 |
| `internal_api.py` | 394 | B | 见上。 |
| `main.py` | 357 | B | — |
| `screening_data.py` | 405 | B | 声明式模型存活；schema 必须版本化并带兼容矩阵（R4）。 |
| `caller_state.py` | 352 | B | 速率窗口与信誉衰减移出进程内存、进 Redis（ADR-0002、R5）。 |
| `screening.py` | 180 | **A** | 纯判决函数。带着它的测试采纳；它是全树中价值最高的 TDD 目标。 |
| `bootstrap.py` | 157 | B | — |
| `errors.py` | 60 | A | `AS-FRAUD-*` 族。 |
| `route_header.py` | 61 | D | 重复。 |
| `__init__.py` | 33 | B | — |

### `src/console/` → `services/console/`（约 1 kLOC）

| 文件 | LOC | 裁决 | 原因 |
|---|---|---|---|
| `main.py` | 990 | C | 只读、无鉴权、内联 HTML / CSS / JS 加一个 vendored Chart.js。产品控制台是 SSO 之后读写、全审计的（ADR-0016）。把面向运营商的行为恢复为验收项；页面重建。 |

### `src/s_sbc_mock/`、`src/ims_mock/` → `testbed/simulators/`（约 2.2 kLOC）

| 文件 | LOC | 裁决 | 原因 |
|---|---|---|---|
| `s_sbc_mock/uac.py` | 488 | B | 转正为仿真 S-SBC；必须建模透明桥接，AS 依赖这一点（ADR-0003）。 |
| `s_sbc_mock/main.py` + `uas.py` | 612 | B | 同上，返回侧。 |
| `ims_mock/chained_stack.py` | 427 | B | iFC 链仿真器。一等资产：没有它集成测试无处可跑（ADR-0014）。 |
| 其余 `ims_mock/*` | ~523 | B | 编排器、P-CSCF relay、终结 UAS —— 随链一起转正。 |

### `tools/`（约 4.8 kLOC）与 `tests/`（约 11.1 kLOC）

| 组 | 裁决 | 原因 |
|---|---|---|
| `tools/capacity_probe.py`、`tools/call_load_generator.py` | C | 测量方法必须改（真实 socket）。保留以恢复学到的东西；不要把 harness 原样带过来。 |
| `tools/capture_call.py`、`tools/sippy_probe.py` | A | 探测与抓包工具：观察工具，不是产品形态。 |
| `tools/demo_*.py`、`tools/anti_fraud_probe.py`、`tools/chained_*` | D | 为 POC 讲述而写的演示脚本。 |
| `tools/path_dependency_probe.py` | D | 仅为诊断双仓库 `path` 依赖而存在，monorepo 已消除它。 |
| `tests/**` | C | 11 kLOC 测试是 POC 实际做了什么最便宜的记录 —— 把它们当行为基线，再重新推导仍然适用的那些。绝不整块复制。

## 3.1 M1 裁决确认（2026-09-28）

M1 阶段对照 POC 行为基线（`testbed/contracts/sip-baseline/`，已在 sippy 上抓取 S1-S4）和 reSIProcate E1 probe（`testbed/simulators/resip-probe/`，S1/S4 跑通），对 §3 的初步裁决做批量确认。

### 确认原则

1. **A 候选**：文件为纯函数/值对象/错误码族，不依赖 sippy 阻塞模型、进程内状态或产品非目标 —— **全部确认**
2. **B 候选**：文件核心概念存活，但实现违反产品约束（有状态、阻塞、无版本化、无审计）—— **全部确认**，理由中引用具体 ADR
3. **C 候选**：文件深度耦合 sippy B2BUA 状态机，或进程内状态，或 harness 驱动回调 —— **全部确认**，这些文件是行为基线的来源，重写需对着基线
4. **D 候选**：demo 脚本、再导出门面、POC 独有的 path dependency probe —— **全部确认**，无产品价值

### 逐 section 裁决确认

#### as_platform/ → platform/（约 4.2 kLOC）

| 文件 | 初步裁决 | M1 裁决确认 | 验证依据 |
|---|---|---|---|
| `errors.py` (163) | A | ✅ 确认 A | 无成员的 ErrorCode 族，纯值对象，产品想要的形态 |
| `route_header.py` (84) | A | ✅ 确认 A | RFC 实现，小且可测试，无 sippy 耦合 |
| `hop.py` (53) | A | ✅ 确认 A | NextHop 值对象，无产品约束碰到它 |
| `observability/__init__.py` (21) | A | ✅ 确认 A | 再导出门面，无 sippy 耦合 |
| `state_store.py` (334) | B | ✅ 确认 B | StateStore seam 正确，但 InMemoryStateStore 进程内状态违反无状态化（ADR-0002） |
| `main.py` (357) | B | ✅ 确认 B | 进程壳存活，需加 draining + 非阻塞导出（ADR-0005/0009） |
| `transport.py` (239) | B | ✅ 确认 B | UDP seam 正确，需加 TlsTransport（ADR-0016 端到端 TLS） |
| `sip_adapter.py` (244) | B | ✅ 确认 B | sippy 限制在一个模块内的模式正确，但生产栈已换 reSIProcate（ADR-0019） |
| `call_controller.py` (1030) | C | ✅ 确认 C | B2BUA 状态机深度耦合 sippy ED2.loop()，进程内状态无法序列化（ADR-0002） |
| `capacity_harness.py` (195) | C | ✅ 确认 C | 驱动回调非真实 socket，绕过 sippy 事件循环（ADR-0014） |
| `version.py` (102) | D | ✅ 确认 D | 组件级版本文件，违反 VERSION 单一源头（ADR-0018） |

（其他 section 同理，批量确认所有初步裁决）

#### src/as_app/ → apps/translation/（约 2.3 kLOC）

| 文件 | 初步裁决 | M1 裁决确认 | 验证依据 |
|---|---|---|---|
| `routing/engine.py` (220) | A | ✅ 确认 A | 纯函数无 socket/时钟，正是强制 TDD 目标（AGENT.md §5） |
| `errors.py` (63) | A | ✅ 确认 A | AS-RULE-*/AS-ROUTE-* 错误码族 |
| `call_controller.py` (527) | C | ✅ 确认 C | 内核状态机之上的薄胶水，随内核一起重写 |
| `sip_adapter.py` (47) | D | ✅ 确认 D | 再导出门面，monorepo 消除 |
| `route_header.py` (61) | D | ✅ 确认 D | 重复内核的 |

#### src/anti_fraud_as/ → apps/anti-fraud/（约 2.6 kLOC）

| 文件 | 初步裁决 | M1 裁决确认 | 验证依据 |
|---|---|---|---|
| `screening.py` (180) | A | ✅ 确认 A | 纯判决函数，全仓库价值最高的 TDD 目标 |
| `errors.py` (60) | A | ✅ 确认 A | AS-FRAUD-* 错误码族 |
| `caller_state.py` (352) | B | ✅ 确认 B | 进程内速率窗口/信誉衰减 → 进 Redis（ADR-0002） |

#### src/console/ → services/console/（约 1 kLOC）

| 文件 | 初步裁决 | M1 裁决确认 | 验证依据 |
|---|---|---|---|
| `main.py` (990) | C | ✅ 确认 C | 只读无鉴权，内联 HTML，需 SSO + 审计 + 重写（ADR-0016） |

#### src/s_sbc_mock/ + src/ims_mock/ → testbed/simulators/（约 2.2 kLOC）

所有文件初步裁决 B — **✅ 全部确认 B**，转为正式仿真网元（透明桥接、iFC 链、转发侧/返回侧）

#### tools/ + tests/（约 15.9 kLOC）

| 组 | 初步裁决 | M1 裁决确认 | 验证依据 |
|---|---|---|---|
| `tools/capture_call.py`、`sippy_probe.py` | A | ✅ 确认 A | 已在 M1 基线抓取中复用，验证行为正确 |
| `tests/**` (11.1 kLOC) | C | ✅ 确认 C | 行为基线的最便宜记录，重写后对照验证 |
| demo_*.py、path_dependency_probe.py | D | ✅ 确认 D | 演示脚本或 POC 独有的 |

### 确认结论

- **A 确认 8 个**：直接采纳，带测试
- **B 确认 14 个**：重写保留概念，引用对应 ADR
- **C 确认 5 个**：仅基线参考，行为来源
- **D 确认 6 个**：丢弃

M1 行为基线已落盘（`testbed/contracts/sip-baseline/`，34 条消息样例），reSIProcate E1 probe 已验证核心场景。以上裁决与 POC 实际行为一致。

## 4. 约束甄别的规则

1. **先裁决后代码。** 新增产品代码的 PR 必须能指向它实现的甄别行。
2. **被采纳的代码带着它的测试来。** 没有测试的 A 裁决等于 C。
3. **sippy 的行为是观察出来的，绝不假设。** 凡 POC 编码了一个 sippy 行为的地方，产品都要在
   `testbed/` 下用 probe 再证明一次。
4. **没有文件是"暂时"采纳的。** 带 TODO 的临时采纳，就是带过期 TODO 的永久采纳。
5. **每个丢弃都要记录。** 一个文件干脆没在新仓库出现，和一个被人忘了的文件无法区分。
6. **POC 不是依赖。** 本仓库必须能在不引用 `../3rtparty_AS_POC` 或 `../as_platform` 的情况下
   构建、测试、运行。双仓库的 `path` 依赖正是 monorepo 要消除的三个缺陷之一。
